-- Plataforma Psicossocial V2 - Supabase/Postgres
-- Modelo inicial preparado para multiempresa, multiciclo, auditoria e relatórios.

create extension if not exists pgcrypto;

create type public.user_role as enum ('owner', 'admin', 'psychologist', 'consultant', 'client');
create type public.company_status as enum ('active', 'inactive', 'suspended');
create type public.campaign_status as enum ('draft', 'collecting', 'closed', 'approved', 'generating', 'generated', 'cancelled');
create type public.payment_status as enum ('pending', 'confirmed', 'waived', 'refunded');
create type public.question_type as enum ('likert_frequency', 'open_text', 'single_choice', 'number');
create type public.question_direction as enum ('risk', 'protective', 'neutral');
create type public.alert_severity as enum ('info', 'attention', 'high', 'critical');
create type public.alert_status as enum ('open', 'reviewing', 'resolved', 'dismissed');
create type public.action_item_status as enum ('planned', 'in_progress', 'done', 'cancelled');

create table public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    full_name text,
    email text,
    role public.user_role not null default 'client',
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.companies (
    id uuid primary key default gen_random_uuid(),
    public_code text not null unique,
    legal_name text not null,
    trade_name text,
    cnpj text,
    responsible_name text,
    responsible_email text,
    status public.company_status not null default 'active',
    lgpd_controller_name text,
    lgpd_contact_email text,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.company_members (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references public.companies(id) on delete cascade,
    user_id uuid not null references public.profiles(id) on delete cascade,
    role public.user_role not null default 'client',
    active boolean not null default true,
    created_at timestamptz not null default now(),
    unique(company_id, user_id)
);

create table public.questionnaires (
    id uuid primary key default gen_random_uuid(),
    code text not null unique,
    version text not null,
    title text not null,
    status text not null default 'draft',
    methodology_status text not null,
    source_notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.domains (
    id uuid primary key default gen_random_uuid(),
    questionnaire_id uuid not null references public.questionnaires(id) on delete cascade,
    code text not null,
    name text not null,
    description text,
    sort_order integer not null,
    created_at timestamptz not null default now(),
    unique(questionnaire_id, code)
);

create table public.questions (
    id uuid primary key default gen_random_uuid(),
    questionnaire_id uuid not null references public.questionnaires(id) on delete cascade,
    domain_id uuid references public.domains(id) on delete set null,
    code text not null,
    text text not null,
    question_type public.question_type not null default 'likert_frequency',
    direction public.question_direction not null default 'risk',
    is_critical boolean not null default false,
    is_required boolean not null default true,
    sort_order integer not null,
    created_at timestamptz not null default now(),
    unique(questionnaire_id, code)
);

create table public.campaigns (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references public.companies(id) on delete cascade,
    questionnaire_id uuid not null references public.questionnaires(id),
    code text not null unique,
    title text not null,
    cycle_year integer,
    status public.campaign_status not null default 'draft',
    payment_status public.payment_status not null default 'pending',
    employees_contracted integer not null default 0,
    expected_respondents integer,
    price_per_employee numeric(12,2) default 0,
    minimum_price numeric(12,2) default 0,
    min_group_size integer not null default 7,
    recommended_group_size integer not null default 10,
    min_participation_warning numeric(4,3) not null default 0.700,
    min_participation_strong_warning numeric(4,3) not null default 0.500,
    access_token_hash text,
    starts_at timestamptz,
    closes_at timestamptz,
    closed_at timestamptz,
    approved_at timestamptz,
    generated_at timestamptz,
    created_by uuid references public.profiles(id),
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.campaign_sectors (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references public.campaigns(id) on delete cascade,
    sector_name text not null,
    expected_headcount integer,
    reportable boolean not null default true,
    created_at timestamptz not null default now(),
    unique(campaign_id, sector_name)
);

create table public.responses (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references public.campaigns(id) on delete cascade,
    submitted_at timestamptz not null default now(),
    sector text,
    role_family text,
    work_unit text,
    demographics jsonb not null default '{}'::jsonb,
    consent_accepted boolean not null default true,
    dedupe_hash text,
    source text not null default 'streamlit',
    created_at timestamptz not null default now(),
    unique(campaign_id, dedupe_hash)
);

create table public.response_items (
    id uuid primary key default gen_random_uuid(),
    response_id uuid not null references public.responses(id) on delete cascade,
    question_id uuid not null references public.questions(id) on delete restrict,
    raw_value text,
    numeric_score numeric(6,2),
    exposure_score numeric(6,2),
    created_at timestamptz not null default now(),
    unique(response_id, question_id)
);

create table public.open_answers (
    id uuid primary key default gen_random_uuid(),
    response_id uuid not null references public.responses(id) on delete cascade,
    question_id uuid references public.questions(id) on delete set null,
    prompt_code text not null,
    raw_text text,
    redacted_text text,
    theme_tags text[] not null default '{}',
    reviewed_by uuid references public.profiles(id),
    released_to_report boolean not null default false,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz
);

create table public.organizational_metrics (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references public.campaigns(id) on delete cascade,
    sector text,
    metric_type text not null,
    metric_label text not null,
    value numeric(14,4),
    unit text,
    period_start date,
    period_end date,
    source text,
    notes text,
    created_at timestamptz not null default now()
);

create table public.reports (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references public.campaigns(id) on delete cascade,
    scope_type text not null,
    scope_name text not null,
    storage_bucket text,
    storage_path text,
    file_name text,
    sha256 text,
    report_version text not null,
    visible_to_client boolean not null default true,
    respondents_count integer,
    generated_by uuid references public.profiles(id),
    generated_at timestamptz not null default now(),
    metadata jsonb not null default '{}'::jsonb
);

create table public.alerts (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references public.campaigns(id) on delete cascade,
    scope_type text not null default 'company',
    scope_name text,
    severity public.alert_severity not null default 'attention',
    code text not null,
    title text not null,
    description text not null,
    evidence jsonb not null default '{}'::jsonb,
    status public.alert_status not null default 'open',
    reviewed_by uuid references public.profiles(id),
    reviewed_at timestamptz,
    created_at timestamptz not null default now()
);

create table public.action_plans (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references public.campaigns(id) on delete cascade,
    title text not null,
    status text not null default 'draft',
    owner_notes text,
    created_by uuid references public.profiles(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.action_items (
    id uuid primary key default gen_random_uuid(),
    action_plan_id uuid not null references public.action_plans(id) on delete cascade,
    domain_code text,
    priority integer not null default 3,
    description text not null,
    rationale text,
    owner_name text,
    due_date date,
    status public.action_item_status not null default 'planned',
    indicator text,
    evidence_link text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.audit_logs (
    id uuid primary key default gen_random_uuid(),
    actor_id uuid references public.profiles(id),
    actor_type text not null default 'system',
    company_id uuid references public.companies(id) on delete set null,
    campaign_id uuid references public.campaigns(id) on delete set null,
    action text not null,
    details jsonb not null default '{}'::jsonb,
    ip_hash text,
    user_agent text,
    created_at timestamptz not null default now()
);

create index idx_company_members_user on public.company_members(user_id) where active = true;
create index idx_campaigns_company on public.campaigns(company_id);
create index idx_responses_campaign on public.responses(campaign_id);
create index idx_response_items_response on public.response_items(response_id);
create index idx_reports_campaign on public.reports(campaign_id);
create index idx_alerts_campaign on public.alerts(campaign_id, status);
create index idx_audit_campaign on public.audit_logs(campaign_id, created_at desc);

create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger trg_profiles_updated before update on public.profiles for each row execute function public.touch_updated_at();
create trigger trg_companies_updated before update on public.companies for each row execute function public.touch_updated_at();
create trigger trg_questionnaires_updated before update on public.questionnaires for each row execute function public.touch_updated_at();
create trigger trg_campaigns_updated before update on public.campaigns for each row execute function public.touch_updated_at();
create trigger trg_action_plans_updated before update on public.action_plans for each row execute function public.touch_updated_at();
create trigger trg_action_items_updated before update on public.action_items for each row execute function public.touch_updated_at();

create or replace view public.v_campaign_response_counts as
select
    c.id as campaign_id,
    c.company_id,
    count(r.id)::integer as responses_count,
    count(distinct nullif(r.sector, ''))::integer as sectors_with_responses,
    case
        when c.expected_respondents is null or c.expected_respondents = 0 then null
        else round(count(r.id)::numeric / c.expected_respondents, 4)
    end as participation_rate
from public.campaigns c
left join public.responses r on r.campaign_id = c.id
group by c.id, c.company_id, c.expected_respondents;
