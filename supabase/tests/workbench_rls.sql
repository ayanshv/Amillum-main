-- Run against an isolated Supabase test database after the migration.
-- All fixtures are rolled back. Requires a migration/test administrator connection.
begin;
insert into auth.users(id,email) values
 ('11111111-1111-4111-8111-111111111111','workbench-a@example.test'),
 ('22222222-2222-4222-8222-222222222222','workbench-b@example.test');
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
select set_config('request.jwt.claims','{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}',true);
select * from public.save_workbench_item(
 '{"id":"33333333-3333-4333-8333-333333333333","type":"obligation","title":"Give notice","document_id":"44444444-4444-4444-8444-444444444444"}',
 '{"id":"44444444-4444-4444-8444-444444444444","kind":"document","title":"Lease.pdf"}');
-- A lost-response retry must not duplicate the item.
select * from public.save_workbench_item(
 '{"id":"33333333-3333-4333-8333-333333333333","type":"obligation","title":"Give notice","document_id":"44444444-4444-4444-8444-444444444444"}',
 '{"id":"44444444-4444-4444-8444-444444444444","kind":"document","title":"Lease.pdf"}');
do $$ begin
 if (select count(*) from public.workbench_items) <> 1 then raise exception 'Retry duplicated item'; end if;
 if (select user_id from public.workbench_items limit 1) <> auth.uid() then raise exception 'Wrong owner'; end if;
 begin
  insert into public.workbench_items(user_id,type,title) values ('22222222-2222-4222-8222-222222222222','note','Forged owner');
  raise exception 'Forged ownership accepted';
 exception when insufficient_privilege then null; end;
 begin
  update public.workbench_items set user_id='22222222-2222-4222-8222-222222222222';
  raise exception 'Ownership transfer accepted';
 exception when insufficient_privilege then null; end;
 begin
  insert into public.workbench_items(type,title,due_date) values ('deadline','Unconfirmed','2026-10-01');
  raise exception 'Unconfirmed date accepted';
 exception when check_violation then null; end;
end $$;
update public.workbench_items set status='completed',due_date='2026-10-01',date_confirmed=true where id='33333333-3333-4333-8333-333333333333';
do $$ begin
 if (select count(*) from public.workbench_items where status='completed' and type='obligation' and due_date='2026-10-01') <> 1 then
  raise exception 'Completion/filter/date failed'; end if;
end $$;
select set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
select set_config('request.jwt.claims','{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}',true);
do $$ declare affected integer; begin
 if exists(select from public.workbench_items) or exists(select from public.workbench_sources) then raise exception 'Cross-user read'; end if;
 update public.workbench_items set title='Stolen' where id='33333333-3333-4333-8333-333333333333';
 get diagnostics affected = row_count;
 if affected<>0 then raise exception 'Cross-user update'; end if;
 delete from public.workbench_items where id='33333333-3333-4333-8333-333333333333';
 get diagnostics affected = row_count;
 if affected<>0 then raise exception 'Cross-user delete'; end if;
 begin
  insert into public.workbench_items(type,title,document_id) values ('note','Wrong source','44444444-4444-4444-8444-444444444444');
  raise exception 'Cross-user source accepted';
 exception when foreign_key_violation then null; end;
 begin
  perform public.save_workbench_item('{"id":"33333333-3333-4333-8333-333333333333","type":"note","title":"Steal through RPC"}',null);
  raise exception 'RPC bypassed RLS';
 exception when insufficient_privilege then null; end;
 begin
  perform public.save_workbench_item('{"id":"55555555-5555-4555-8555-555555555555","user_id":"11111111-1111-4111-8111-111111111111","type":"note","title":"Forged RPC"}',null);
  raise exception 'RPC accepted owner';
 exception when insufficient_privilege then null; end;
end $$;
set local role anon;
select set_config('request.jwt.claim.sub','',true);
select set_config('request.jwt.claims','{}',true);
do $$ begin
 begin perform * from public.workbench_items; raise exception 'Anonymous read'; exception when insufficient_privilege then null; end;
 begin insert into public.workbench_items(type,title) values ('note','Anonymous'); raise exception 'Anonymous insert'; exception when insufficient_privilege then null; end;
 begin update public.workbench_items set title='Anonymous'; raise exception 'Anonymous update'; exception when insufficient_privilege then null; end;
 begin delete from public.workbench_items; raise exception 'Anonymous delete'; exception when insufficient_privilege then null; end;
end $$;
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
select set_config('request.jwt.claims','{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}',true);
delete from public.workbench_items where id='33333333-3333-4333-8333-333333333333';
do $$ begin if exists(select from public.workbench_items) then raise exception 'Owner delete failed'; end if; end $$;
rollback;
