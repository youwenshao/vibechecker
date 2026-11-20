-- Run against a database with the Phase 0 schema and Supabase roles.
begin;
set local role service_role;
do $$
begin
  for i in 1..10 loop
    assert public.consume_quota('test-device','test-address');
  end loop;
  assert not public.consume_quota('test-device','test-address');
  assert (select used = 10 from public.quota_usage where subject='a:test-address');
  assert public.use_retry('test-retry');
  assert not public.use_retry('test-retry');
  perform public.record_heartbeat('new',now());
  perform public.record_heartbeat('old',now()-interval '1 minute');
  assert (select engine_version='new' from public.engine_status where id='primary');
  perform public.store_check('e63d7237-2906-49b9-a04c-c319bc9bf53d','test-key','test-claim','test','mlx-cpu','{"wordCount":170}');
  perform public.store_check('e63d7237-2906-49b9-a04c-c319bc9bf53d','test-key','test-claim','test','mlx-cpu','{"wordCount":170}');
  assert (select count(*)=1 from public.checks where claim_token_hash='test-claim');
  assert not has_function_privilege('anon','public.consume_quota(text,text)','execute');
  assert not has_table_privilege('authenticated','public.checks','select');
end $$;
rollback;
