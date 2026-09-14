begin;
insert into auth.users(id,email) values ('11111111-1111-4111-8111-111111111111','a@example.test'),('22222222-2222-4222-8222-222222222222','b@example.test');
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
do $$ declare i integer;begin
 if public.get_entitlements()->>'plan'<>'free' then raise exception 'Default plan';end if;
 if public.consume_ai_allowance('email_drafting')<>'denied' then raise exception 'Free email bypass';end if;
 for i in 1..5 loop
  if public.consume_ai_allowance('document_analysis')<>'allowed' then raise exception 'Free value missing';end if;
 end loop;
 if public.consume_ai_allowance('document_analysis')<>'limit' then raise exception 'Limit bypass';end if;
 if public.consume_ai_allowance('ai_questions','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')<>'allowed' then raise exception 'Request denied';end if;
 if public.consume_ai_allowance('ai_questions','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')<>'duplicate' then raise exception 'Duplicate charged';end if;
 begin update public.ai_usage set used=0;raise exception 'Usage mutation allowed';exception when insufficient_privilege then null;end;
 begin insert into public.subscriptions(user_id,customer_id,plan_id) values(auth.uid(),'forged','grand');raise exception 'Plan spoofing';exception when insufficient_privilege then null;end;
 begin perform public.reserve_checkout(auth.uid(),'forged');raise exception 'Privileged function exposed';exception when insufficient_privilege then null;end;
end $$;
reset role;
select public.reserve_checkout('11111111-1111-4111-8111-111111111111','cus_a');
select public.sync_subscription('cus_a','sub_a','monthly','trialing',now()-interval '1 hour',now()+interval '7 days',false,100);
set local role authenticated;
do $$ begin
 if public.get_entitlements()->>'plan'<>'monthly' then raise exception 'Trial access missing';end if;
 if public.consume_ai_allowance('email_drafting')<>'allowed' then raise exception 'Email unavailable';end if;
end $$;
select set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
do $$ begin
 if exists(select 1 from public.subscriptions) or exists(select 1 from public.ai_usage) then raise exception 'Cross-user read';end if;
 if public.get_entitlements()->>'plan'<>'free' then raise exception 'Cross-user entitlement';end if;
 begin update public.subscriptions set plan_id='grand';raise exception 'Cross-user update';exception when insufficient_privilege then null;end;
 begin delete from public.subscriptions;raise exception 'Cross-user delete';exception when insufficient_privilege then null;end;
end $$;
reset role;
select public.sync_subscription('cus_a','sub_a','monthly','past_due',now()-interval '1 hour',now()+interval '7 days',false,101);
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
do $$ begin
 if public.get_entitlements()->>'plan'<>'free' then raise exception 'Failed payment granted access';end if;
end $$;
reset role;
select public.sync_subscription('cus_a','sub_a','grand','active',now()-interval '1 hour',now()+interval '7 days',false,100);
set local role authenticated;
do $$ begin
 if public.get_entitlements()->>'plan'<>'free' then raise exception 'Stale event restored access';end if;
end $$;
reset role;
select public.sync_subscription('cus_a','sub_a','monthly','trialing',now()-interval '8 days',now()-interval '1 day',false,102);
set local role authenticated;
do $$ begin
 if public.get_entitlements()->>'status'<>'expired' then raise exception 'Trial expiry bypass';end if;
end $$;
reset role;
select public.sync_subscription('cus_a','sub_a','monthly','canceled',now()-interval '8 days',now()-interval '1 day',false,103);
update public.subscriptions set checkout_until=now()-interval '1 second';
do $$ begin
 if (public.reserve_checkout('11111111-1111-4111-8111-111111111111','cus_a')->>'trial')::boolean then raise exception 'Repeated trial';end if;
end $$;

select public.sync_subscription('cus_a','sub_b','weekly','active',now()-interval '1 hour',now()+interval '6 days',false,104);
set local role authenticated;
do $$ begin
 if public.consume_ai_allowance('email_drafting')<>'allowed' then raise exception 'Paid drafting';end if;
end $$;
reset role;
select public.sync_subscription('cus_a','sub_b','monthly','active',now(),now()+interval '1 month',false,105);
set local role authenticated;
do $$ begin
 if (public.get_entitlements()->'features'->'email_drafting'->>'used')::integer<1 then raise exception 'Upgrade erased usage';end if;
end $$;
reset role;
do $$ begin
 begin delete from auth.users where id='11111111-1111-4111-8111-111111111111';raise exception 'Orphan billing allowed';exception when insufficient_privilege then null;end;
end $$;
set local role authenticated;
select set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
do $$ declare i integer;begin
 for i in 1..20 loop
  insert into public.workbench_items(title,type) values ('Synthetic item','note');
 end loop;
 begin insert into public.workbench_items(title,type) values ('Over cap','note');raise exception 'Workbench cap bypass';exception when insufficient_privilege then null;end;
end $$;
reset role;
set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
do $$ declare i integer; result text; limited boolean:=false;begin
 for i in 1..45 loop
  result:=public.consume_ai_allowance('ai_questions');
  if result='rate_limit' then limited:=true;exit;end if;
 end loop;
 if not limited then raise exception 'Rate limit bypass';end if;
end $$;
set local role anon;
do $$ begin
 begin perform public.get_entitlements();raise exception 'Anonymous entitlement access';exception when insufficient_privilege then null;end;
end $$;
rollback;
