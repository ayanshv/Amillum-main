begin;
insert into auth.users(id,email) values ('11111111-1111-4111-8111-111111111111','a@test.invalid'),('22222222-2222-4222-8222-222222222222','b@test.invalid');
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
insert into public.profiles(display_name) values('A');
insert into public.user_settings(privacy) values('{"excluded":["com.test.app"]}');
update public.profiles set display_name='Updated';
do $$ begin
 if (select display_name from public.profiles)<>'Updated' then raise exception 'Profile update failed'; end if;
 begin
 insert into public.profiles(user_id,display_name) values('22222222-2222-4222-8222-222222222222','Forged');
 raise exception 'Forged owner accepted';
 exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
do $$ begin
 if exists(select 1 from public.profiles) or exists(select 1 from public.user_settings) then raise exception 'Cross user read'; end if;
end $$;
update public.profiles set display_name='Stolen';
delete from public.user_settings;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
do $$ begin
 if (select display_name from public.profiles)<>'Updated' or (select count(*) from public.user_settings)<>1 then raise exception 'Cross user mutation'; end if;
 begin
 perform public.delete_own_account('DELETE MY ACCOUNT');
 raise exception 'Deletion without recent password allowed';
 exception when raise_exception then
 if SQLERRM <> 'Recent password authentication required' then raise; end if;
 end;
end $$;
select set_config('request.jwt.claims',jsonb_build_object('amr',jsonb_build_array(jsonb_build_object('method','password','timestamp',extract(epoch from now()))))::text,true);
do $$ begin
 begin perform public.delete_own_account(null); raise exception 'Null confirmation accepted';
 exception when raise_exception then if SQLERRM <> 'Explicit authenticated confirmation required' then raise; end if; end;
end $$;
select public.delete_own_account('DELETE MY ACCOUNT');
reset role;
do $$ begin
 if exists(select 1 from auth.users where id='11111111-1111-4111-8111-111111111111') or exists(select 1 from public.profiles) or exists(select 1 from public.user_settings) then raise exception 'Deletion incomplete'; end if;
 if not exists(select 1 from auth.users where id='22222222-2222-4222-8222-222222222222') then raise exception 'Other user deleted'; end if;
end $$;
set local role anon;
do $$ begin
 begin perform * from public.profiles; raise exception 'Anonymous profile access'; exception when insufficient_privilege then null; end;
 begin perform public.delete_own_account('DELETE MY ACCOUNT'); raise exception 'Anonymous deletion'; exception when insufficient_privilege then null; end;
end $$;
rollback;
