begin;
-- Catalog is deployed from backend/config/plans.json; clients cannot edit it.
create table public.billing_plans(id text primary key check(id in ('free','weekly','monthly','grand')), config jsonb not null);
alter table public.billing_plans enable row level security;
grant select on public.billing_plans to anon,authenticated;
create policy public_catalog on public.billing_plans for select using(true);
create table public.subscriptions (
 user_id uuid primary key references auth.users(id) on delete cascade,
 customer_id text unique not null,
 subscription_id text unique,
 plan_id text not null default 'free' references public.billing_plans(id),
 status text not null default 'free',
 period_start timestamptz, period_end timestamptz,
 cancel_at_period_end boolean not null default false,
 trial_used boolean not null default false,
 event_created bigint not null default 0,
 checkout_key uuid, checkout_until timestamptz,
 updated_at timestamptz not null default now()
);
alter table public.subscriptions enable row level security;
alter table public.subscriptions force row level security;
revoke all on public.subscriptions from public,anon,authenticated;
grant select on public.subscriptions to authenticated;
create policy subscription_owner on public.subscriptions for select to authenticated using(user_id=auth.uid());
grant all on public.subscriptions,public.billing_plans to service_role;
-- Extend M15 usage in place. Existing counters are retained.
alter table public.ai_usage add column period_start timestamptz;
update public.ai_usage set period_start=month::timestamptz;
alter table public.ai_usage alter column period_start set not null;
alter table public.ai_usage drop constraint ai_usage_pkey;
alter table public.ai_usage add primary key(user_id,feature,period_start);
create table public.ai_requests (
 user_id uuid not null references auth.users(id) on delete cascade,
 request_id uuid not null, feature text not null, created_at timestamptz not null default now(),
 primary key(user_id,request_id)
);
alter table public.ai_requests enable row level security;
revoke all on public.ai_requests from public,anon,authenticated;
-- No content or model results are stored in request deduplication records.
create function public.get_entitlements() returns jsonb language plpgsql security definer set search_path='' as $$
declare u uuid:=auth.uid(); s public.subscriptions; p jsonb; start_at timestamptz; end_at timestamptz;
 effective text:='free'; state text:='free'; f record; used_count integer; result jsonb:='{}';
begin
 if u is null then raise exception 'Authentication required' using errcode='42501';end if;
 select * into s from public.subscriptions where user_id=u;
 start_at:=date_trunc('month',now() at time zone 'UTC') at time zone 'UTC';end_at:=start_at+interval '1 month';
 if s.user_id is not null then
  state:=s.status;
  if s.status in ('active','trialing') and s.period_start<=now() and s.period_end>now() then
   effective:=s.plan_id;start_at:=s.period_start;end_at:=s.period_end;
  elsif s.status in ('active','trialing') then state:='expired';end if;
 end if;
 select config into p from public.billing_plans where id=effective;
 if p is null then raise exception 'Entitlements unavailable' using errcode='55000';end if;
 for f in select * from jsonb_each(p->'features') loop
  if f.key='legal_workbench' then select count(*) into used_count from public.workbench_items where user_id=u;
  else select coalesce(sum(used),0) into used_count from public.ai_usage where user_id=u and feature=f.key and period_start>=start_at and period_start<end_at;end if;
  result:=result||jsonb_build_object(f.key,f.value||jsonb_build_object('used',used_count,'remaining',greatest(0,(f.value->>'limit')::integer-used_count)));
 end loop;
 return jsonb_build_object('plan',effective,'status',state,'period_start',start_at,'reset_at',end_at,'cancel_at_period_end',coalesce(s.cancel_at_period_end,false),'features',result,'rate_per_minute',(p->>'rate_per_minute')::integer);
end $$;
revoke all on function public.get_entitlements() from public,anon;
grant execute on function public.get_entitlements() to authenticated;
drop function public.consume_ai_allowance(text);
create function public.consume_ai_allowance(requested_feature text, request_id uuid default null) returns text
language plpgsql security definer set search_path='' as $$
declare u uuid:=auth.uid(); e jsonb; f jsonb; start_at timestamptz;
begin
 if u is null then return 'denied';end if;
 -- Serializes concurrent usage, webhook transitions, and Workbench insertion per user.
 perform pg_advisory_xact_lock(hashtextextended(u::text,0));
 e:=public.get_entitlements();f:=e->'features'->requested_feature;
 if f is null or not (f->>'enabled')::boolean or not (f->>'available')::boolean then return 'denied';end if;
 if not (f->>'metered')::boolean then return 'allowed';end if;
 if request_id is not null and exists(select 1 from public.ai_requests r where r.user_id=u and r.request_id=consume_ai_allowance.request_id) then return 'duplicate';end if;
 if (select count(*) from public.ai_requests where user_id=u and created_at>now()-interval '1 minute')>=coalesce((e->>'rate_per_minute')::integer,0) then return 'rate_limit';end if;
 if (f->>'remaining')::integer<=0 then return 'limit';end if;
 start_at:=(e->>'period_start')::timestamptz;
 insert into public.ai_usage(user_id,feature,month,period_start,used) values(u,requested_feature,start_at::date,start_at,1)
 on conflict(user_id,feature,period_start) do update set used=public.ai_usage.used+1;
 insert into public.ai_requests(user_id,request_id,feature) values(u,coalesce(request_id,gen_random_uuid()),requested_feature);
 return 'allowed';
end $$;
revoke all on function public.consume_ai_allowance(text,uuid) from public,anon;
grant execute on function public.consume_ai_allowance(text,uuid) to authenticated;
-- Direct PostgREST writes cannot bypass the Workbench item cap. Read/edit/delete stay available after downgrade.
create function public.workbench_plan_limit() returns trigger language plpgsql security definer set search_path='' as $$
declare e jsonb;
begin
 perform pg_advisory_xact_lock(hashtextextended(new.user_id::text,0));
 if exists(select 1 from public.workbench_items where id=new.id and user_id=new.user_id) then return new;end if;
 if auth.uid() is distinct from new.user_id then raise exception 'Ownership required' using errcode='42501';end if;
 e:=public.get_entitlements();
 if not coalesce((e->'features'->'legal_workbench'->>'enabled')::boolean,false) or not coalesce((e->'features'->'legal_workbench'->>'available')::boolean,false) or (e->'features'->'legal_workbench'->>'remaining')::integer<=0 then raise exception 'Workbench limit reached. Manage your plan on the Amillum website.' using errcode='42501';end if;
 return new;
end $$;
create trigger workbench_plan_cap before insert on public.workbench_items for each row execute function public.workbench_plan_limit();
revoke all on function public.workbench_plan_limit() from public,anon,authenticated;
-- Backend-only billing transaction. An abandoned Checkout does not grant access or a second trial.
create function public.reserve_checkout(p_user uuid,p_customer text) returns jsonb language plpgsql security definer set search_path='' as $$
declare s public.subscriptions; trial boolean;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_user::text,0));
 insert into public.subscriptions(user_id,customer_id) values(p_user,p_customer) on conflict(user_id) do nothing;
 select * into s from public.subscriptions where user_id=p_user for update;
 if s.customer_id<>p_customer then raise exception 'Customer mismatch';end if;
 if s.subscription_id is not null and s.status not in ('canceled','expired','incomplete_expired') then raise exception 'Manage existing subscription through portal';end if;
 if s.checkout_until>now() then raise exception 'Checkout already pending. Wait for it to expire before trying again.';end if;
 trial:=not s.trial_used;
 update public.subscriptions set checkout_key=gen_random_uuid(),checkout_until=now()+interval '31 minutes',trial_used=true where user_id=p_user returning * into s;
 return jsonb_build_object('key',s.checkout_key,'trial',trial);
end $$;
revoke all on function public.reserve_checkout(uuid,text) from public,anon,authenticated;
grant execute on function public.reserve_checkout(uuid,text) to service_role;
create function public.sync_subscription(p_customer text,p_subscription text,p_plan text,p_status text,p_start timestamptz,p_end timestamptz,p_cancel boolean,p_event bigint)
returns boolean language plpgsql security definer set search_path='' as $$
declare s public.subscriptions;
begin
 select * into s from public.subscriptions where customer_id=p_customer;
 if s.user_id is null then raise exception 'Unknown customer';end if;
 perform pg_advisory_xact_lock(hashtextextended(s.user_id::text,0));
 select * into s from public.subscriptions where customer_id=p_customer for update;
 if p_event<s.event_created then return false;end if;
 if s.subscription_id is not null and s.subscription_id<>p_subscription and s.status not in ('canceled','expired','incomplete_expired') then raise exception 'Conflicting subscription';end if;
 -- A plan change during an active period carries usage forward, including interval changes.
 if s.status='active' and p_status='active' and s.plan_id<>p_plan and s.period_end>now() and s.period_start<>p_start then
  insert into public.ai_usage(user_id,feature,month,period_start,used)
  select user_id,feature,p_start::date,p_start,sum(used)::integer from public.ai_usage
  where user_id=s.user_id and period_start>=s.period_start and period_start<s.period_end and period_start<>p_start
  group by user_id,feature
  on conflict(user_id,feature,period_start) do update set used=greatest(public.ai_usage.used,excluded.used);
 end if;
 update public.subscriptions set subscription_id=p_subscription,plan_id=p_plan,status=p_status,period_start=p_start,period_end=p_end,cancel_at_period_end=p_cancel,event_created=p_event,trial_used=true,updated_at=now() where user_id=s.user_id;
 return true;
end $$;
revoke all on function public.sync_subscription(text,text,text,text,timestamptz,timestamptz,boolean,bigint) from public,anon,authenticated;
grant execute on function public.sync_subscription(text,text,text,text,timestamptz,timestamptz,boolean,bigint) to service_role;
-- Do not orphan a recurring Stripe subscription when the Auth user is deleted.
create function public.protect_billed_account_delete() returns trigger language plpgsql security definer set search_path='' as $$
begin
 if exists(select 1 from public.subscriptions where user_id=old.id and subscription_id is not null and status not in ('canceled','incomplete_expired')) then
  raise exception 'Cancel your subscription on the Amillum website and wait until cancellation is effective before deleting your account.' using errcode='42501';
 end if;
 return old;
end $$;
create trigger protect_billed_account before delete on auth.users for each row execute function public.protect_billed_account_delete();
revoke all on function public.protect_billed_account_delete() from public,anon,authenticated;
commit;
