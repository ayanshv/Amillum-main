-- Apply once using Supabase migrations or the project's SQL editor.
-- No document bodies, screenshots, or AI transcripts are stored here.
begin;
create table public.workbench_sources (
  id uuid not null,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  kind text not null check (kind in ('document','selection')),
  title text not null check (char_length(btrim(title)) between 1 and 240),
  created_at timestamptz not null default now(),
  primary key (id,user_id)
);
create table public.workbench_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  document_id uuid,
  type text not null check (type in ('task','obligation','deadline','question','attention','note')),
  title text not null check (char_length(btrim(title)) between 1 and 200),
  description text not null default '' check (char_length(description) <= 4000),
  source_context text not null default '' check (char_length(source_context) <= 500),
  status text not null default 'open' check (status in ('open','completed','dismissed')),
  due_date date,
  date_confirmed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (document_id,user_id) references public.workbench_sources(id,user_id),
  check (due_date is null or date_confirmed)
);
create index workbench_owner_status on public.workbench_items(user_id,status,type,created_at desc);
create index workbench_document on public.workbench_items(user_id,document_id);

alter table public.workbench_items enable row level security;
alter table public.workbench_items force row level security;
alter table public.workbench_sources enable row level security;
alter table public.workbench_sources force row level security;
revoke all on public.workbench_items, public.workbench_sources from anon, public;
revoke all on public.workbench_items, public.workbench_sources from authenticated;
grant select,delete on public.workbench_items to authenticated;
grant insert(id,document_id,type,title,description,source_context,status,due_date,date_confirmed)
  on public.workbench_items to authenticated;
grant update(document_id,type,title,description,source_context,status,due_date,date_confirmed)
  on public.workbench_items to authenticated;
grant select on public.workbench_sources to authenticated;
grant insert(id,kind,title) on public.workbench_sources to authenticated;

create policy workbench_read_own on public.workbench_items for select to authenticated using ((select auth.uid())=user_id);
create policy workbench_insert_own on public.workbench_items for insert to authenticated with check ((select auth.uid())=user_id);
create policy workbench_update_own on public.workbench_items for update to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy workbench_delete_own on public.workbench_items for delete to authenticated using ((select auth.uid())=user_id);
create policy sources_read_own on public.workbench_sources for select to authenticated using ((select auth.uid())=user_id);
create policy sources_insert_own on public.workbench_sources for insert to authenticated with check ((select auth.uid())=user_id);

create function public.workbench_touch_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at = now();
  return new;
end;
$$;
create trigger workbench_updated before update on public.workbench_items
  for each row execute function public.workbench_touch_updated_at();

-- Atomic source + item save. The caller's JWT and RLS apply inside this function.
-- A stable item UUID makes a retry safe even if the first response was lost.
create function public.save_workbench_item(p_item jsonb, p_source jsonb default null)
returns setof public.workbench_items language plpgsql security invoker set search_path = '' as $$
begin
  if auth.uid() is null then raise exception 'Authentication required' using errcode='42501'; end if;
  if p_item ? 'user_id' or (p_source is not null and p_source ? 'user_id') then
    raise exception 'Ownership is assigned by the authenticated session' using errcode='42501';
  end if;
  if p_source is not null then
    if (p_source->>'id')::uuid is distinct from (p_item->>'document_id')::uuid then
      raise exception 'Source mismatch' using errcode='23514';
    end if;
    insert into public.workbench_sources(id,kind,title)
      values ((p_source->>'id')::uuid,p_source->>'kind',p_source->>'title')
      on conflict (id,user_id) do nothing;
  end if;
  return query insert into public.workbench_items
    (id,document_id,type,title,description,source_context,status,due_date,date_confirmed)
    values ((p_item->>'id')::uuid,(p_item->>'document_id')::uuid,p_item->>'type',p_item->>'title',
      coalesce(p_item->>'description',''),coalesce(p_item->>'source_context',''),
      coalesce(p_item->>'status','open'),(p_item->>'due_date')::date,coalesce((p_item->>'date_confirmed')::boolean,false))
    on conflict (id) do update set type=excluded.type,title=excluded.title,description=excluded.description,
      source_context=excluded.source_context,status=excluded.status,due_date=excluded.due_date,
      date_confirmed=excluded.date_confirmed,document_id=excluded.document_id
    returning *;
end;
$$;
revoke all on function public.save_workbench_item(jsonb,jsonb) from public,anon;
grant execute on function public.save_workbench_item(jsonb,jsonb) to authenticated;
revoke all on function public.workbench_touch_updated_at() from public,anon;
commit;
