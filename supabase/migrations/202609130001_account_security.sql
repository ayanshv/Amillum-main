-- 12B: harden existing Amillum user-owned tables; do not invent missing products.
begin;
do $$
declare target_table text; owner_column text;
begin
 foreach target_table in array array['profiles','documents','analyses','workbench_items','workbench_sources','user_settings','usage','subscriptions'] loop
  if to_regclass('public.'||target_table) is null then continue; end if;
  owner_column := case when exists(select 1 from information_schema.columns c where c.table_schema='public' and c.table_name=target_table and c.column_name='user_id') then 'user_id'
    when target_table='profiles' and exists(select 1 from information_schema.columns c where c.table_schema='public' and c.table_name=target_table and c.column_name='id') then 'id' else null end;
  if owner_column is null then raise exception 'Ownership column must be audited for table %',target_table; end if;
  execute format('alter table public.%I enable row level security',target_table);
  execute format('alter table public.%I force row level security',target_table);
  execute format('revoke all on public.%I from anon, public',target_table);
  execute format('create policy amillum_owner_boundary on public.%I as restrictive for all to authenticated using ((select auth.uid())=%I) with check ((select auth.uid())=%I)',target_table,owner_column,owner_column);
  if target_table in ('usage','subscriptions') then
   execute format('revoke insert,update,delete on public.%I from authenticated',target_table);
  end if;
 end loop;
end $$;
commit;
