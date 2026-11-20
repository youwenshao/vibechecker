-- Run against a database with the Phase 0 schema and Supabase roles.
begin;
do $$
begin
  assert exists (
    select from cron.job where jobname='vibechecker-retention'
    and schedule='17 * * * *' and active
  ), 'hourly retention job is active';
  assert (select count(*)=5 and bool_and(c.relrowsecurity)
    from pg_catalog.pg_class c join pg_catalog.pg_namespace ns on ns.oid=c.relnamespace
    where ns.nspname='public' and c.relname in
      ('checks','result_cache','engine_status','quota_usage','retry_usage')), 'all service tables have RLS';
end $$;
set local role service_role;
do $$
declare
  fixture_time timestamptz := greatest(now(), (select last_seen from public.engine_status where id='primary')) + interval '1 second';
  table_name text;
  app_role text;
  proc text;
begin
  for i in 1..10 loop
    assert public.consume_quota('test-device','test-address');
  end loop;
  assert not public.consume_quota('test-device','test-address');
  assert (select used = 10 from public.quota_usage where subject='a:test-address');
  update public.quota_usage set used = 299 where subject = 'a:test-address';
  assert public.consume_quota('another-test-device','test-address');
  assert not public.consume_quota('third-test-device','test-address');
  assert not exists (select from public.quota_usage where subject='d:third-test-device');
  assert public.use_retry('test-retry');
  assert not public.use_retry('test-retry');
  perform public.record_heartbeat('new',fixture_time);
  perform public.record_heartbeat('old',fixture_time-interval '1 minute');
  assert (select engine_version='new' from public.engine_status where id='primary');
  perform public.store_check('e63d7237-2906-49b9-a04c-c319bc9bf53d','test-key','test-claim','test','mlx-cpu','{"wordCount":170}');
  perform public.store_check('e63d7237-2906-49b9-a04c-c319bc9bf53d','test-key','test-claim','test','mlx-cpu','{"wordCount":170}');
  assert (select count(*)=1 from public.checks where claim_token_hash='test-claim');
  assert (select result = '{"wordCount":170}'::jsonb and backend='mlx-cpu'
    and expires_at=now()+interval '30 days' from public.result_cache where key='test-key');
  assert (select word_count=170 and user_id is null and result='{"wordCount":170}'::jsonb
    and expires_at=now()+interval '30 days' from public.checks where claim_token_hash='test-claim');
  foreach app_role in array array['anon','authenticated'] loop
    foreach table_name in array array['checks','result_cache','engine_status','quota_usage','retry_usage'] loop
      assert not has_table_privilege(app_role,'public.' || table_name,'select,insert,update,delete');
    end loop;
    foreach proc in array array[
      'public.consume_quota(text,text)', 'public.use_retry(text)',
      'public.record_heartbeat(text,timestamptz)', 'public.store_check(uuid,text,text,text,text,jsonb)'
    ] loop
      assert not has_function_privilege(app_role, proc, 'execute');
    end loop;
  end loop;
end $$;
rollback;
