-- Catálogo organizacional, snapshot por campanha e ciência versionada.
-- Migration incremental: execute depois de 001_initial_schema.sql e
-- 002_rls_policies.sql. Nenhuma coluna legada é removida.

begin;

-- ---------------------------------------------------------------------------
-- Catálogo vigente da empresa: cada área aponta para um grupo canônico.
-- ---------------------------------------------------------------------------
create table if not exists public.company_areas (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references public.companies(id) on delete cascade,
    area_name text not null check (btrim(area_name) <> ''),
    area_key text not null check (btrim(area_key) <> ''),
    analysis_group_key text not null check (btrim(analysis_group_key) <> ''),
    analysis_group_name text not null check (btrim(analysis_group_name) <> ''),
    active boolean not null default true,
    sort_order integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(company_id, area_key)
);

create index if not exists idx_company_areas_company_active
    on public.company_areas(company_id, active, sort_order, area_name);
create index if not exists idx_company_areas_group
    on public.company_areas(company_id, analysis_group_key)
    where active = true;

alter table public.company_areas enable row level security;

drop policy if exists "company_areas_read_members" on public.company_areas;
create policy "company_areas_read_members" on public.company_areas
for select using (public.is_company_member(company_id));

drop trigger if exists trg_company_areas_updated on public.company_areas;
create trigger trg_company_areas_updated
before update on public.company_areas
for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- campaign_sectors permanece como tabela de snapshot. As novas colunas
-- distinguem a opção concreta (área) do grupo usado nos relatórios.
-- ---------------------------------------------------------------------------
alter table public.campaign_sectors
    add column if not exists company_area_id uuid
        references public.company_areas(id) on delete set null,
    add column if not exists area_name text,
    add column if not exists area_key text,
    add column if not exists analysis_group_key text,
    add column if not exists analysis_group_name text,
    add column if not exists sort_order integer not null default 0;

-- Dados legados são preservados como mapeamento 1:1. Se uma linha antiga já
-- estiver no formato "Área | Grupo", a separação também é reconhecida.
update public.campaign_sectors
set area_name = coalesce(
        nullif(btrim(area_name), ''),
        btrim(split_part(sector_name, ' | ', 1))
    ),
    analysis_group_name = coalesce(
        nullif(btrim(analysis_group_name), ''),
        case
            when strpos(sector_name, ' | ') > 0
                then btrim(substr(sector_name, strpos(sector_name, ' | ') + 3))
            else btrim(sector_name)
        end
    )
where area_name is null
   or btrim(area_name) = ''
   or analysis_group_name is null
   or btrim(analysis_group_name) = '';

update public.campaign_sectors
set area_key = coalesce(
        nullif(btrim(area_key), ''),
        coalesce(
            nullif(lower(btrim(regexp_replace(area_name, '[^[:alnum:]]+', '_', 'g'))), ''),
            'area'
        )
    ),
    analysis_group_key = coalesce(
        nullif(btrim(analysis_group_key), ''),
        coalesce(
            nullif(lower(btrim(regexp_replace(analysis_group_name, '[^[:alnum:]]+', '_', 'g'))), ''),
            'grupo'
        )
    )
where area_key is null
   or btrim(area_key) = ''
   or analysis_group_key is null
   or btrim(analysis_group_key) = '';

create index if not exists idx_campaign_sectors_area
    on public.campaign_sectors(campaign_id, area_key);
create index if not exists idx_campaign_sectors_group
    on public.campaign_sectors(campaign_id, analysis_group_key);

-- ---------------------------------------------------------------------------
-- Token de participação separado e snapshot exato do aviso.
-- code continua sendo o token legado/painel para não quebrar integrações.
-- ---------------------------------------------------------------------------
alter table public.campaigns
    add column if not exists response_code text,
    add column if not exists notice_version text,
    add column if not exists notice_controller text,
    add column if not exists notice_operator text,
    add column if not exists notice_contact text,
    add column if not exists notice_retention text,
    add column if not exists notice_body text,
    add column if not exists notice_content_sha256 text,
    add column if not exists notice_frozen_at timestamptz,
    add column if not exists structure_frozen_at timestamptz;

-- Continuidade operacional: links existentes continuam válidos até que o
-- administrador rotacione response_code para um valor realmente distinto.
update public.campaigns
set response_code = code
where response_code is null;

create unique index if not exists uq_campaigns_response_code
    on public.campaigns(response_code)
    where response_code is not null;

-- ---------------------------------------------------------------------------
-- Respostas guardam somente o grupo canônico, nunca a área selecionada.
-- O ID da área é usado pelo servidor apenas durante a validação.
-- ---------------------------------------------------------------------------
alter table public.responses
    add column if not exists analysis_group_key text,
    add column if not exists analysis_group_name text,
    add column if not exists current_job_title text,
    add column if not exists notice_version text,
    add column if not exists notice_content_sha256 text,
    add column if not exists notice_accepted_at timestamptz;

update public.responses
set analysis_group_name = coalesce(nullif(btrim(analysis_group_name), ''), nullif(btrim(sector), '')),
    analysis_group_key = coalesce(
        nullif(btrim(analysis_group_key), ''),
        nullif(lower(btrim(regexp_replace(coalesce(sector, ''), '[^[:alnum:]]+', '_', 'g'))), '')
    ),
    current_job_title = coalesce(current_job_title, role_family)
where analysis_group_name is null
   or analysis_group_key is null
   or current_job_title is null;

-- Ausência de consentimento nunca mais é interpretada como aceite. Respostas
-- históricas não recebem versão/horário artificialmente.
alter table public.responses
    alter column consent_accepted set default false;

create index if not exists idx_responses_campaign_group
    on public.responses(campaign_id, analysis_group_key);
create index if not exists idx_responses_campaign_notice
    on public.responses(campaign_id, notice_version, consent_accepted);

-- Integridade também no banco: para campanhas com aviso configurado, inserts
-- diretos precisam carregar a mesma versão/hash e um aceite anterior ao envio.
create or replace function public.validate_response_notice_and_group()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    campaign_notice_version text;
    campaign_notice_hash text;
begin
    select c.notice_version, c.notice_content_sha256
      into campaign_notice_version, campaign_notice_hash
      from public.campaigns c
     where c.id = new.campaign_id;

    if nullif(btrim(campaign_notice_version), '') is not null then
        if new.consent_accepted is not true then
            raise exception 'A ciência afirmativa do aviso é obrigatória.';
        end if;
        if nullif(btrim(new.notice_version), '') is null
           or new.notice_version <> campaign_notice_version then
            raise exception 'A versão aceita do aviso não corresponde à campanha.';
        end if;
        if new.notice_accepted_at is null then
            raise exception 'O momento da ciência do aviso é obrigatório.';
        end if;
        if new.notice_accepted_at > coalesce(new.submitted_at, now()) then
            raise exception 'A ciência do aviso deve ocorrer antes do envio.';
        end if;
        if nullif(btrim(campaign_notice_hash), '') is not null
           and coalesce(new.notice_content_sha256, '') <> campaign_notice_hash then
            raise exception 'O conteúdo aceito do aviso não corresponde à campanha.';
        end if;
    end if;

    if nullif(btrim(new.analysis_group_key), '') is not null
       and not exists (
           select 1
             from public.campaign_sectors cs
            where cs.campaign_id = new.campaign_id
              and cs.analysis_group_key = new.analysis_group_key
       ) then
        raise exception 'O grupo de análise não pertence à campanha.';
    end if;

    return new;
end;
$$;

drop trigger if exists trg_validate_response_notice_and_group on public.responses;
create trigger trg_validate_response_notice_and_group
before insert or update of campaign_id, consent_accepted, notice_version,
    notice_content_sha256, notice_accepted_at, analysis_group_key
on public.responses
for each row execute function public.validate_response_notice_and_group();

commit;
