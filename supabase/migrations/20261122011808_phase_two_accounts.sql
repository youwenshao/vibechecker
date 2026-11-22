create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

create table public.profiles (
  id uuid primary key references auth.users on delete cascade,
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;
revoke all on public.profiles from public, anon, authenticated;
grant select on public.profiles to authenticated;
create policy "read own profile" on public.profiles for select to authenticated
using (id = (select auth.uid()));

create function private.create_profile() returns trigger language plpgsql security definer
set search_path = '' as $$
begin
  insert into public.profiles(id) values (new.id) on conflict do nothing;
  return new;
end $$;
revoke all on function private.create_profile() from public, anon, authenticated;
create trigger create_profile after insert on auth.users for each row execute function private.create_profile();
insert into public.profiles(id) select id from auth.users on conflict do nothing;

alter table public.checks alter column claim_token_hash drop not null;
create index checks_owner_expiry on public.checks(user_id, expires_at desc);
grant select(id, mode, word_count, engine_version, result, expires_at, user_id), delete on public.checks to authenticated;
create policy "read own current checks" on public.checks for select to authenticated
using (user_id = (select auth.uid()) and expires_at > now());
create policy "delete own checks" on public.checks for delete to authenticated using (user_id = (select auth.uid()));

create table private.check_texts (
  check_id uuid primary key references public.checks on delete cascade,
  envelope jsonb not null
);
alter table private.check_texts enable row level security;
revoke all on private.check_texts from public, anon, authenticated;
grant select, insert, delete on private.check_texts to service_role;

create function public.claim_check(p_id uuid, p_hash text, p_owner uuid) returns boolean
language plpgsql set search_path = '' as $$
begin
  update public.checks set user_id=p_owner, claim_token_hash=null
    where id=p_id and user_id is null and expires_at>now() and claim_token_hash=p_hash;
  return found;
end $$;

-- Store only bounded numeric detector signals. There is no check or account key.
create table public.feature_log (
  sequence bigint generated always as identity primary key,
  day date not null default ((now() at time zone 'UTC')::date),
  mode text not null, engine_version text not null, features jsonb not null
);
alter table public.feature_log enable row level security;
revoke all on public.feature_log from public,anon,authenticated;
grant insert,select,delete on public.feature_log to service_role;
grant usage on sequence public.feature_log_sequence_seq to service_role;
create index feature_log_day_sequence on public.feature_log(day,sequence);
select cron.schedule('vibechecker-feature-retention','20 0 * * *',$job$
  delete from public.feature_log where day <= (now() at time zone 'UTC')::date - 7;
$job$);

create function public.store_account_check(
  p_id uuid, p_key text, p_claim_hash text, p_version text, p_backend text, p_result jsonb,
  p_mode text, p_owner uuid, p_envelope jsonb
) returns void language plpgsql set search_path = '' as $$
begin
  if p_envelope is not null and p_owner is null then raise exception 'Account required'; end if;
  insert into public.checks(id,user_id,claim_token_hash,mode,engine_version,backend,word_count,result)
    values (p_id,p_owner,case when p_owner is null then p_claim_hash end,p_mode,p_version,p_backend,(p_result->>'wordCount')::int,p_result)
    on conflict(id) do nothing;
  if not found then return; end if;
  insert into public.feature_log(mode,engine_version,features)
    select p_mode,p_version,jsonb_object_agg(s->>'id',s->'value')
    from jsonb_array_elements(p_result->'signals') s
    where s->>'id' in ('e1','e2','e3','e4','e5','e6','e7','stylometry')
      and jsonb_typeof(s->'value')='number'
    having count(*)>0;
  if p_envelope is not null then
    insert into private.check_texts values (p_id,p_envelope);
  end if;
  insert into public.result_cache as c(key,backend,result) values (p_key,p_backend,p_result)
    on conflict(key) do update set result=excluded.result,backend=excluded.backend,expires_at=excluded.expires_at
    where c.expires_at<=now();
end $$;

create function public.read_saved_essay(p_id uuid,p_owner uuid) returns jsonb
language sql stable set search_path = '' as $$
  select t.envelope from private.check_texts t join public.checks c on c.id=t.check_id
    where c.id=p_id and c.user_id=p_owner and c.expires_at>now();
$$;

create function public.check_quota(p_device text,p_address text,p_mode text,p_member boolean) returns boolean
language plpgsql set search_path = '' as $$
declare
  today date := (now() at time zone 'Asia/Hong_Kong')::date;
  device_key text;
  address_key text;
  device_cap int;
  address_cap int;
  n int;
begin
  case p_mode
    when 'quick' then device_key:='d:'||p_device; address_key:='a:'||p_address; address_cap:=300;
      device_cap:=case when p_member then 30 else 10 end;
    when 'deep' then device_key:='deep:'||p_device; address_key:='a:deep:'||p_address; address_cap:=60;
      device_cap:=case when p_member then 10 else 3 end;
    else raise exception 'Unknown mode';
  end case;
  insert into public.quota_usage(subject,day) values(address_key,today) on conflict do nothing;
  select used into n from public.quota_usage where subject=address_key and day=today for update;
  if n>=address_cap then return false; end if;
  insert into public.quota_usage(subject,day) values(device_key,today) on conflict do nothing;
  select used into n from public.quota_usage where subject=device_key and day=today for update;
  if n>=device_cap then return false; end if;
  update public.quota_usage set used=used+1 where day=today and subject in (address_key,device_key);
  return true;
end $$;
create function public.device_usage(p_device text) returns jsonb language sql stable set search_path = '' as $$
  select jsonb_build_object('quick',coalesce(max(used) filter(where subject='d:'||p_device),0),
    'deep',coalesce(max(used) filter(where subject='deep:'||p_device),0))
  from public.quota_usage where day=(now() at time zone 'Asia/Hong_Kong')::date
    and subject in ('d:'||p_device,'deep:'||p_device);
$$;
revoke all on function public.claim_check(uuid,text,uuid), public.read_saved_essay(uuid,uuid),
  public.store_account_check(uuid,text,text,text,text,jsonb,text,uuid,jsonb),
  public.check_quota(text,text,text,boolean), public.device_usage(text) from public,anon,authenticated;
grant execute on function public.claim_check(uuid,text,uuid), public.read_saved_essay(uuid,uuid),
  public.store_account_check(uuid,text,text,text,text,jsonb,text,uuid,jsonb),
  public.check_quota(text,text,text,boolean), public.device_usage(text) to service_role;
