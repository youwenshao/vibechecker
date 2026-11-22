"use client";
import { useEffect, useState, type FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { CheckResult, Mode } from "@vibechecker/contracts";
import { deviceChecks, forgetOne, forgetOwner, saveCheck } from "../lib/device";
import { Verification } from "./Verification";
import { LensPanel } from "./LensPanel";
import { CautionText } from "./CautionText";
import { Signals } from "./Instruments";
import { EvidenceKit } from "./EvidenceKit";
import { SentenceHeatmap } from "./SentenceHeatmap";

type Row = {
  id: string;
  mode: Mode;
  engine_version: string;
  expires_at: string;
  word_count: number;
};
type Listing = { owner: string | null; rows?: Row[]; more?: boolean };
type Detail = { id: string; result: CheckResult; text: string | null; local: boolean; row: Row };
type Removal = { action: "delete"; id: string } | { action: "deleteAll" | "deleteAccount" };

async function post(path: string, body: unknown) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw Error("Request failed");
  return res.json();
}
const action = (cmd: unknown) => post("/api/account", cmd);
async function list(before?: Row): Promise<Listing> {
  const cursor = before
    ? "?before=" + encodeURIComponent(JSON.stringify([before.expires_at, before.id]))
    : "";
  const res = await fetch("/api/account" + cursor, { cache: "no-store" });
  if (!res.ok) throw Error("History unavailable");
  return res.json();
}

export function History() {
  const t = useTranslations(),
    locale = useLocale();
  const [data, setData] = useState<Listing>();
  const [detail, setDetail] = useState<Detail>();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState(""),
    [token, setToken] = useState(""),
    [challenge, setChallenge] = useState(0);
  const [pending, setPending] = useState<Removal>();
  useEffect(() => {
    let live = true;
    async function init() {
      let current = await list();
      if (current.owner) {
        const owner = current.owner;
        try {
          for (const record of await deviceChecks()) {
            if (!live) return;
            if (record.owner || !record.claimToken) continue;
            const { claimed } = await action({
              action: "claim",
              id: record.checkId,
              token: record.claimToken,
            });
            if (claimed || current.rows?.some((row) => row.id === record.checkId))
              await saveCheck({ ...record, owner, claimToken: "" });
          }
          current = await list();
        } catch {
          if (live) setMessage("account.claimError");
        }
      } else if (new URLSearchParams(location.search).has("auth") && live)
        setMessage("account.expired");
      if (live) setData(current);
    }
    init().catch(() => {
      if (live) setMessage("account.error");
    });
    return () => {
      live = false;
    };
  }, []);
  async function perform(work: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await work();
    } catch {
      setMessage("account.error");
    } finally {
      setBusy(false);
    }
  }
  function login(provider: "email" | "google", event?: FormEvent) {
    event?.preventDefault();
    void perform(async () => {
      try {
        const answer = await post("/api/auth/start", { provider, email, token, locale });
        if (provider === "google") location.assign(answer.url);
        else setMessage("account.sent");
      } finally {
        setToken("");
        setChallenge((n) => n + 1);
      }
    });
  }
  function open(row: Row) {
    void perform(async () => {
      const response = await action({ action: "read", id: row.id });
      const device = response.text == null ? await deviceChecks().catch(() => []) : [];
      const local = device.find((item) => item.checkId === row.id && item.owner === data?.owner);
      setDetail({
        row,
        id: row.id,
        result: response.result,
        text: response.text ?? local?.text ?? null,
        local: Boolean(local),
      });
    });
  }
  function remove(cmd: Removal) {
    void perform(async () => {
      await action(cmd);
      setPending(undefined);
      setDetail(undefined);
      if (cmd.action === "delete") await forgetOne(cmd.id);
      else if (data?.owner) await forgetOwner(data.owner);
      setData(await list());
      setMessage("account.done");
    });
  }
  const formatDate = (date: string) =>
    new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(date));
  return (
    <>
      <h1>{t("account.title")}</h1>
      {message && (
        <p role="status" className="notice">
          {t(message)}
        </p>
      )}
      {!data ? (
        <p>{t("account.loading")}</p>
      ) : !data.owner ? (
        <section className="account-card">
          <p>{t("account.intro")}</p>
          <form onSubmit={(e) => login("email", e)}>
            <label htmlFor="email">{t("account.email")}</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              required
              maxLength={320}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Verification key={challenge} mode="auth" onToken={setToken} />
            <div className="account-actions">
              <button className="primary" disabled={busy || !token}>
                {t("account.magic")}
              </button>
              <button
                className="pill"
                type="button"
                disabled={busy || !token}
                onClick={() => login("google")}
              >
                {t("account.google")}
              </button>
            </div>
          </form>
        </section>
      ) : (
        <>
          <p>{t("account.retention")}</p>
          {detail ? (
            <section className="account-card">
              <button className="text-button" onClick={() => setDetail(undefined)}>
                {t("account.close")}
              </button>
              <h2>
                {t("result.title")} · {detail.result.index}/100
              </h2>
              <p>{t("result.range", detail.result.interval)}</p>
              <p className="caution">
                <CautionText />
              </p>
              {(["why", "wrong"] as const).map((k) => (
                <details key={k}>
                  <summary>{t("result." + k)}</summary>
                  <p>{t("result." + k + "Body")}</p>
                </details>
              ))}
              {detail.result.flags.length > 0 && (
                <section className="flags">
                  <h3>{t("result.flags")}</h3>
                  <ul>
                    {detail.result.flags.map((flag) => (
                      <li key={flag}>{t("result." + flag)}</li>
                    ))}
                  </ul>
                </section>
              )}
              <Signals result={detail.result} />
              <LensPanel result={detail.result} />
              {detail.text ? (
                <details>
                  <summary>{t(detail.local ? "account.local" : "account.text")}</summary>
                  <p className="saved-text">{detail.text}</p>
                </details>
              ) : (
                <p>{t("account.noText")}</p>
              )}
              {detail.text && detail.result.sentences && (
                <SentenceHeatmap
                  text={detail.text}
                  sentences={detail.result.sentences}
                  streaming={false}
                />
              )}
              <EvidenceKit
                result={detail.result}
                mode={detail.row.mode}
                version={detail.row.engine_version}
                date={Date.parse(detail.row.expires_at) - 30 * 86400000}
              />
            </section>
          ) : (
            <>
              {!data.rows?.length && <p className="account-card">{t("account.empty")}</p>}
              <ul className="history-list">
                {data.rows?.map((row) => (
                  <li key={row.id}>
                    <div>
                      <strong>
                        {t("home." + row.mode)} · {t("home.count", { n: row.word_count })}
                      </strong>
                      <p>{t("account.expires", { date: formatDate(row.expires_at) })}</p>
                    </div>
                    <div className="account-actions">
                      <button disabled={busy} className="pill" onClick={() => open(row)}>
                        {t("account.open")}
                      </button>
                      <button
                        disabled={busy}
                        className="text-button"
                        onClick={() => setPending({ action: "delete", id: row.id })}
                      >
                        {t("account.remove")}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
              {data.more && (
                <button
                  className="pill"
                  disabled={busy}
                  onClick={() =>
                    void perform(async () => {
                      const next = await list(data.rows?.at(-1));
                      setData({ ...next, rows: [...(data.rows ?? []), ...(next.rows ?? [])] });
                    })
                  }
                >
                  {t("account.more")}
                </button>
              )}
            </>
          )}
          <div className="account-actions">
            <button
              className="pill"
              disabled={busy}
              onClick={() =>
                void perform(async () => {
                  await action({ action: "signOut" });
                  setDetail(undefined);
                  setPending(undefined);
                  setData({ owner: null });
                })
              }
            >
              {t("account.signOut")}
            </button>
            {(["deleteAll", "deleteAccount"] as const).map((k) => (
              <button
                key={k}
                className="text-button"
                disabled={busy}
                onClick={() => setPending({ action: k })}
              >
                {t(k === "deleteAll" ? "account.all" : "account.account")}
              </button>
            ))}
          </div>
          {pending && (
            <section className="notice" aria-live="polite">
              <p>
                {t(
                  {
                    delete: "account.confirmOne",
                    deleteAll: "account.confirmAll",
                    deleteAccount: "account.confirmAccount",
                  }[pending.action],
                )}
              </p>
              <button className="pill" disabled={busy} onClick={() => remove(pending)}>
                {t("account.confirm")}
              </button>
              <button className="text-button" disabled={busy} onClick={() => setPending(undefined)}>
                {t("account.cancel")}
              </button>
            </section>
          )}
        </>
      )}
    </>
  );
}
