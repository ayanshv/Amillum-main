-- Operator-managed entitlements. No client can grant itself access or increase limits.
begin;
create table if not exists public.ai_allowances (
 user_id uuid not null references auth.users(id) on delete cascade,
 feature text not null check(feature in ('document_analysis','email_drafting')),
 enabled boolean not null default false,
 monthly_limit integer not null default 0 check(monthly_limit>=0),
 primary key(user_id,feature)
);
create table if not exists public.ai_usage (
 user_id uuid not null references auth.users(id) on delete cascade,
 feature text not null,
 month date not null,
 used integer not null default 0 check(used>=0),
 primary key(user_id,feature,month)
);
alter table public.ai_allowances enable row level security;
alter table public.ai_allowances force row level security;
alter table public.ai_usage enable row level security;
alter table public.ai_usage force row level security;
revoke all on public.ai_allowances,public.ai_usage from public,anon,authenticated;
grant select on public.ai_allowances,public.ai_usage to authenticated;
drop policy if exists allowance_owner on public.ai_allowances;
create policy allowance_owner on public.ai_allowances for select to authenticated using(user_id=auth.uid());
drop policy if exists usage_owner on public.ai_usage;
create policy usage_owner on public.ai_usage for select to authenticated using(user_id=auth.uid());
create or replace function public.consume_ai_allowance(requested_feature text) returns text
language plpgsql security definer set search_path='' as $$
declare identity uuid:=auth.uid(); allowance integer; period date:=date_trunc('month',now() at time zone 'UTC')::date; charged integer;
begin
 if identity is null then return 'denied'; end if;
 select monthly_limit into allowance from public.ai_allowances
 where user_id=identity and feature=requested_feature and enabled for update;
 if allowance is null then return 'denied'; end if;
 if allowance=0 then return 'limit'; end if;
 insert into public.ai_usage(user_id,feature,month,used) values(identity,requested_feature,period,1)
 on conflict(user_id,feature,month) do update set used=public.ai_usage.used+1
 where public.ai_usage.used<allowance returning used into charged;
 if charged is null then return 'limit'; end if;
 return 'allowed';
end $$;
revoke all on function public.consume_ai_allowance(text) from public,anon;
grant execute on function public.consume_ai_allowance(text) to authenticated;
commit;
