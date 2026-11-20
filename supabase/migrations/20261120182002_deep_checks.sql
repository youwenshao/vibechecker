alter table public.checks drop constraint checks_mode_check;
alter table public.checks add constraint checks_mode_check check (
  mode = 'quick' or (mode = 'deep' and word_count between 300 and 2500)
);

create function public.consume_quota(p_device text, p_address text, p_mode text) returns boolean
language plpgsql set search_path = '' as $$
declare
  today date := (now() at time zone 'Asia/Hong_Kong')::date;
  address_key text := 'a:' || p_address;
  device_key text;
  device_limit int;
  used_so_far int;
begin
  case p_mode
    when 'quick' then device_key := 'd:' || p_device; device_limit := 10;
    when 'deep' then device_key := 'deep:' || p_device; device_limit := 3;
    else raise exception 'Invalid check mode';
  end case;
  -- Lock the shared address first in both modes, including requests from older clients.
  insert into public.quota_usage(subject, day) values (address_key,today) on conflict do nothing;
  select used into used_so_far from public.quota_usage where subject=address_key and day=today for update;
  if used_so_far >= 300 then return false; end if;
  insert into public.quota_usage(subject, day) values (device_key,today) on conflict do nothing;
  select used into used_so_far from public.quota_usage where subject=device_key and day=today for update;
  if used_so_far >= device_limit then return false; end if;
  update public.quota_usage set used=used+1 where day=today and subject in (address_key,device_key);
  return true;
end $$;

create or replace function public.consume_quota(p_device text, p_address text) returns boolean
language sql set search_path = '' as $$
  select public.consume_quota(p_device,p_address,'quick');
$$;

create function public.store_check(
  p_id uuid, p_key text, p_claim_hash text, p_version text, p_backend text, p_result jsonb, p_mode text
) returns void language plpgsql set search_path = '' as $$
begin
  insert into public.checks(id,claim_token_hash,mode,engine_version,backend,word_count,result)
  values (p_id,p_claim_hash,p_mode,p_version,p_backend,(p_result->>'wordCount')::int,p_result)
  on conflict (id) do nothing;
  insert into public.result_cache as c(key,backend,result) values (p_key,p_backend,p_result)
  on conflict(key) do update set result=excluded.result, backend=excluded.backend, expires_at=excluded.expires_at
  where c.expires_at <= now();
end $$;

create or replace function public.store_check(
  p_id uuid, p_key text, p_claim_hash text, p_version text, p_backend text, p_result jsonb
) returns void language sql set search_path = '' as $$
  select public.store_check(p_id,p_key,p_claim_hash,p_version,p_backend,p_result,'quick');
$$;

revoke all on function public.consume_quota(text,text,text),public.store_check(uuid,text,text,text,text,jsonb,text)
  from public,anon,authenticated;
grant execute on function public.consume_quota(text,text,text),public.store_check(uuid,text,text,text,text,jsonb,text)
  to service_role;
