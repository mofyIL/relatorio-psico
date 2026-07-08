-- RLS inicial. O backend Streamlit deve usar service_role no servidor.
-- Chaves service_role nunca devem ser expostas ao navegador ou ao repositório.

alter table public.profiles enable row level security;
alter table public.companies enable row level security;
alter table public.company_members enable row level security;
alter table public.questionnaires enable row level security;
alter table public.domains enable row level security;
alter table public.questions enable row level security;
alter table public.campaigns enable row level security;
alter table public.campaign_sectors enable row level security;
alter table public.responses enable row level security;
alter table public.response_items enable row level security;
alter table public.open_answers enable row level security;
alter table public.organizational_metrics enable row level security;
alter table public.reports enable row level security;
alter table public.alerts enable row level security;
alter table public.action_plans enable row level security;
alter table public.action_items enable row level security;
alter table public.audit_logs enable row level security;

create or replace function public.is_platform_admin()
returns boolean language sql stable security definer set search_path = public as $$
    select exists (
        select 1 from public.profiles p
        where p.id = auth.uid()
          and p.active = true
          and p.role in ('owner', 'admin', 'psychologist', 'consultant')
    );
$$;

create or replace function public.is_company_member(target_company_id uuid)
returns boolean language sql stable security definer set search_path = public as $$
    select exists (
        select 1 from public.company_members cm
        where cm.company_id = target_company_id
          and cm.user_id = auth.uid()
          and cm.active = true
    ) or public.is_platform_admin();
$$;

create policy "profiles_read_self_or_admin" on public.profiles
for select using (id = auth.uid() or public.is_platform_admin());

create policy "companies_read_members" on public.companies
for select using (public.is_company_member(id));

create policy "company_members_read_members" on public.company_members
for select using (user_id = auth.uid() or public.is_platform_admin());

create policy "questionnaires_read_authenticated" on public.questionnaires
for select using (auth.role() = 'authenticated');
create policy "domains_read_authenticated" on public.domains
for select using (auth.role() = 'authenticated');
create policy "questions_read_authenticated" on public.questions
for select using (auth.role() = 'authenticated');

create policy "campaigns_read_company_members" on public.campaigns
for select using (public.is_company_member(company_id));

create policy "campaign_sectors_read_company_members" on public.campaign_sectors
for select using (
    exists (select 1 from public.campaigns c where c.id = campaign_id and public.is_company_member(c.company_id))
);

create policy "reports_read_company_members" on public.reports
for select using (
    visible_to_client = true and exists (
        select 1 from public.campaigns c where c.id = campaign_id and public.is_company_member(c.company_id)
    )
);

create policy "alerts_read_admins_only" on public.alerts
for select using (public.is_platform_admin());

create policy "action_plans_read_company_members" on public.action_plans
for select using (
    exists (select 1 from public.campaigns c where c.id = campaign_id and public.is_company_member(c.company_id))
);

create policy "action_items_read_company_members" on public.action_items
for select using (
    exists (
        select 1
        from public.action_plans ap
        join public.campaigns c on c.id = ap.campaign_id
        where ap.id = action_plan_id and public.is_company_member(c.company_id)
    )
);

create policy "audit_logs_read_admins_only" on public.audit_logs
for select using (public.is_platform_admin());

-- Inserções/atualizações devem ser feitas pelo backend com service_role ou por RPCs/Edge Functions específicas.
-- Não há política pública de insert para responses nesta versão inicial para evitar coleta fraudulenta por API aberta.
