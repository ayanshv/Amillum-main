begin;
create table if not exists public.profiles (
 user_id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
 display_name text not null default '' check (length(display_name)<=120),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.user_settings (
 user_id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
 privacy jsonb not null default '{}' check (jsonb_typeof(privacy)='object' and octet_length(privacy::text)<32768),
 updated_at timestamptz not null default now()
);
alter table public.profiles enable row level security;
alter table public.profiles force row level security;
alter table public.user_settings enable row level security;
alter table public.user_settings force row level security;
revoke all on public.profiles,public.user_settings from public,anon,authenticated;
grant select,delete on public.profiles,public.user_settings to authenticated;
grant insert(display_name),update(display_name,updated_at) on public.profiles to authenticated;
grant insert(privacy),update(privacy,updated_at) on public.user_settings to authenticated;
create policy profile_owner on public.profiles for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid());
create policy settings_owner on public.user_settings for all to authenticated using(user_id=auth.uid()) with check(user_id=auth.uid());
-- Password reauthentication is checked in the database, not trusted from the UI.
create function public.delete_own_account(confirmation text) returns void
language plpgsql security definer set search_path='' as $$
declare identity uuid:=auth.uid();
begin
 if identity is null or confirmation is distinct from 'DELETE MY ACCOUNT' then raise exception 'Explicit authenticated confirmation required'; end if;
 if not exists(select 1 from jsonb_array_elements(coalesce(auth.jwt()->'amr','[]')) entry
  where entry->>'method'='password' and (entry->>'timestamp')::numeric > extract(epoch from now())-300)
 then raise exception 'Recent password authentication required'; end if;
 -- Storage blob deletion requires the Storage API. Never claim it happened via SQL.
 if to_regclass('storage.objects') is not null then
  if exists(select 1 from information_schema.columns where table_schema='storage' and table_name='objects' and column_name='owner_id') then
   if exists(select 1 from storage.objects where owner_id=identity::text) then raise exception 'Owned Storage files require backend removal before account deletion'; end if;
  else raise exception 'Storage ownership requires backend review'; end if;
 end if;
 delete from public.workbench_items where user_id=identity;
 delete from public.workbench_sources where user_id=identity;
 delete from auth.users where id=identity;
end $$;
revoke all on function public.delete_own_account(text) from public,anon;
grant execute on function public.delete_own_account(text) to authenticated;
commit;
