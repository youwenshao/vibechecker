begin;
set local role service_role;
do $$
declare
  app_role text;
  score jsonb := '{"wordCount":320,"sentences":[{"start":0,"end":28,"score":0.2,"signals":["e5"]}]}';
begin
  assert public.consume_quota('phase1','test-campus');
  for i in 1..3 loop
    assert public.consume_quota('phase1','test-campus','deep');
  end loop;
  assert not public.consume_quota('phase1','test-campus','deep');
  for i in 2..10 loop
    assert public.consume_quota('phase1','test-campus','quick');
  end loop;
  assert not public.consume_quota('phase1','test-campus');
  assert (select used=13 from public.quota_usage where subject='a:test-campus');
  perform public.store_check('4bf4c4bd-3c45-49b9-9eec-e0ac2a94a692','deep-key','deep-claim','v1','mlx-metal',score,'deep');
  assert (select mode='deep' and result=score from public.checks where claim_token_hash='deep-claim');
  assert (select result=score from public.result_cache where key='deep-key');
  foreach app_role in array array['anon','authenticated'] loop
    assert not has_function_privilege(app_role,'public.consume_quota(text,text,text)','execute');
    assert not has_function_privilege(app_role,'public.store_check(uuid,text,text,text,text,jsonb,text)','execute');
  end loop;
end $$;
rollback;
