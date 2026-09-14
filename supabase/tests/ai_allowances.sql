begin;
insert into auth.users(id,email) values ('11111111-1111-4111-8111-111111111111','a@example.test'),('22222222-2222-4222-8222-222222222222','b@example.test');
insert into public.ai_allowances values('11111111-1111-4111-8111-111111111111','email_drafting',true,2);
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
do $$ begin
 if public.consume_ai_allowance('email_drafting')<>'allowed' then raise exception 'First request failed';end if;
 if public.consume_ai_allowance('email_drafting')<>'allowed' then raise exception 'Second request failed';end if;
 if public.consume_ai_allowance('email_drafting')<>'limit' then raise exception 'Quota bypass';end if;
 if public.consume_ai_allowance('document_analysis')<>'denied' then raise exception 'Feature bypass';end if;
 begin update public.ai_allowances set monthly_limit=999;raise exception 'Client altered allowance';exception when insufficient_privilege then null;end;
end $$;
select set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
do $$ begin
 if exists(select 1 from public.ai_usage) or exists(select 1 from public.ai_allowances) then raise exception 'Cross user access';end if;
 if public.consume_ai_allowance('email_drafting')<>'denied' then raise exception 'Cross user quota';end if;
end $$;
set local role anon;
do $$ begin
 begin perform public.consume_ai_allowance('email_drafting');raise exception 'Anonymous quota access';exception when insufficient_privilege then null;end;
end $$;
reset role;
delete from auth.users where id='11111111-1111-4111-8111-111111111111';
do $$ begin
 if exists(select 1 from public.ai_usage) or exists(select 1 from public.ai_allowances) then raise exception 'Account deletion did not cascade';end if;
end $$;
rollback;
