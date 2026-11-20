-- Quick-only service surface. Claims and owner reads arrive with accounts in Phase 2.
create table public.checks (
  id uuid primary key,
  user_id uuid references auth.users(id) on delete cascade,
  claim_token_hash text not null unique,
  mode text not null default 'quick' check (mode = 'quick'),
  engine_version text not null,
  backend text not null check (backend in ('mlx-cpu','mlx-metal','mlx-cuda')),
  word_count integer not null check (word_count between 150 and 5000),
  result jsonb not null,
  expires_at timestamptz not null default (now() + interval '30 days')
);
create table public.result_cache (
  key text primary key, backend text not null, result jsonb not null,
  expires_at timestamptz not null default (now() + interval '30 days')
);
create table public.quota_usage (
  subject text not null, day date not null, used int not null default 0,
  primary key (subject, day)
);
create table public.engine_status (
  id text primary key check (id = 'primary'), engine_version text not null, last_seen timestamptz not null
);
create table public.retry_usage (
  nonce text primary key, used_at timestamptz not null default now()
);

alter table public.checks enable row level security;
alter table public.result_cache enable row level security;
alter table public.quota_usage enable row level security;
alter table public.engine_status enable row level security;
alter table public.retry_usage enable row level security;

revoke all on public.checks, public.result_cache, public.quota_usage, public.engine_status, public.retry_usage from public, anon, authenticated;
grant select, insert, update, delete on public.checks, public.result_cache, public.quota_usage, public.engine_status, public.retry_usage to service_role;

create function public.consume_quota(p_device text, p_address text) returns boolean
language plpgsql set search_path = '' as $$
declare
  today date := (now() at time zone 'Asia/Hong_Kong')::date;
  device_used int;
  ip_used int;
begin
  -- The address lock serializes devices sharing a campus. Distinct prefixes keep lock order stable.
  insert into public.quota_usage(subject, day) values ('a:' || p_address, today) on conflict do nothing;
  select used into ip_used from public.quota_usage where subject = 'a:' || p_address and day = today for update;
  if ip_used >= 300 then return false; end if;
  insert into public.quota_usage(subject, day) values ('d:' || p_device, today) on conflict do nothing;
  select used into device_used from public.quota_usage where subject = 'd:' || p_device and day = today for update;
  if device_used >= 10 then return false; end if;
  update public.quota_usage set used = used + 1 where day = today and subject in ('a:' || p_address, 'd:' || p_device);
  return true;
end $$;

create function public.use_retry(p_nonce text) returns boolean
language plpgsql set search_path = '' as $$
begin
  insert into public.retry_usage(nonce) values (p_nonce) on conflict do nothing;
  return found;
end $$;

create function public.record_heartbeat(p_version text, p_time timestamptz) returns void
language sql set search_path = '' as $$
  insert into public.engine_status(id,engine_version,last_seen) values ('primary', p_version, p_time)
  on conflict(id) do update set engine_version = excluded.engine_version, last_seen = excluded.last_seen
  where public.engine_status.last_seen < excluded.last_seen;
$$;

create function public.store_check(p_id uuid, p_key text, p_claim_hash text, p_version text, p_backend text, p_result jsonb) returns void
language plpgsql set search_path = '' as $$
begin
  insert into public.checks(id,claim_token_hash,engine_version,backend,word_count,result)
  values (p_id,p_claim_hash,p_version,p_backend,(p_result->>'wordCount')::int,p_result)
  on conflict (id) do nothing;
  insert into public.result_cache as c(key,backend,result) values (p_key,p_backend,p_result)
  on conflict(key) do update set result=excluded.result, backend=excluded.backend, expires_at=excluded.expires_at
  where c.expires_at <= now();
end $$;

revoke all on function public.consume_quota(text,text),public.use_retry(text),public.record_heartbeat(text,timestamptz),public.store_check(uuid,text,text,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.consume_quota(text,text),public.use_retry(text),public.record_heartbeat(text,timestamptz),public.store_check(uuid,text,text,text,text,jsonb) to service_role;
