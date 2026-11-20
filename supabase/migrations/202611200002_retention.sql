create extension if not exists pg_cron;
select cron.schedule('vibechecker-retention', '17 * * * *', $job$
  delete from public.result_cache where expires_at <= now();
  delete from public.checks where expires_at <= now();
  delete from public.retry_usage where used_at < now() - interval '5 minutes';
  delete from public.quota_usage where day < (now() at time zone 'Asia/Hong_Kong')::date - 6;
$job$);
