"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { CheckResult, Mode } from "@vibechecker/contracts";
import { deviceChecks, deviceTtl, forgetOne, forgetOwner, saveCheck, type DeviceCheck } from "../lib/device";
import { sentenceHeats, tonightGlyph } from "../lib/brand";
import { Verification } from "./Verification";
import { LensPanel } from "./LensPanel";
import { Signals } from "./Instruments";
import { EvidenceKit, KitSection } from "./EvidenceKit";
import { SentenceHeatmap } from "./SentenceHeatmap";
import { Icon } from "./Icons";
import { Flags, HouseRule, InfoDialog, ResultHero, type Panel } from "./ResultView";
import { Flyer, PassStage, ThumbFlyer, ThumbPass, type Reading } from "./ResultObjects";

type Row = {
  id: string;
  mode: Mode;
  engine_version: string;
  expires_at: string;
  word_count: number;
  index?: number | null;
  band?: CheckResult["band"] | null;
  interval?: CheckResult["interval"] | null;
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
const issued = (row: Row) => Date.parse(row.expires_at) - deviceTtl;

export function History() {
  const t = useTranslations(),
    locale = useLocale();
  const [data, setData] = useState<Listing>();
  const [detail, setDetail] = useState<Detail>();
  const [device, setDevice] = useState<DeviceCheck[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState(""),
    [token, setToken] = useState(""),
    [challenge, setChallenge] = useState(0);
  const [pending, setPending] = useState<Removal>();
  const [panel, setPanel] = useState<Panel>("why");
  const dialog = useRef<HTMLDialogElement>(null);
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
        const records = await deviceChecks().catch(() => []);
        if (live) setDevice(records.filter((record) => record.owner === owner));
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
      const records = response.text == null ? await deviceChecks().catch(() => []) : [];
      const local = records.find((item) => item.checkId === row.id && item.owner === data?.owner);
      setDetail({
        row,
        id: row.id,
        result: response.result,
        text: response.text ?? local?.text ?? null,
        local: Boolean(local),
      });
      scrollTo({ top: 0 });
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
  function openPanel(value: Panel) {
    setPanel(value);
    dialog.current?.showModal();
  }
  const formatDate = (at: number) => new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(at);
  const heatsFor = (row: Row, slots?: number) =>
    sentenceHeats(device.find((record) => record.checkId === row.id)?.result.sentences, slots);
  const rows = data?.rows ?? [];
  const latest = rows[0];

  const signIn = (
    <div className="account-card plate">
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
          <button type="submit" className="btn btn-primary" disabled={busy || !token}>
            {t("account.magic")}
          </button>
          <button type="button" className="btn" disabled={busy || !token} onClick={() => login("google")}>
            {t("account.google")}
          </button>
        </div>
      </form>
    </div>
  );

  const latestObject = latest && (() => {
    const at = issued(latest);
    const reading: Reading = {
      index: latest.index ?? 0,
      interval: latest.interval ?? { low: 0, high: 100 },
      band: latest.band ?? "mixed",
      wordCount: latest.word_count,
      sentences: device.find((record) => record.checkId === latest.id)?.result.sentences,
    };
    return (
      <div className="history-latest">
        {latest.mode === "deep" ? (
          <PassStage result={reading} at={at} id={latest.id} />
        ) : (
          <div className="result-flyer">
            <Flyer result={reading} at={at} />
          </div>
        )}
        <p className="latest">
          <span>{t("account.latest")}</span>
          <span>{t("account.expires", { date: formatDate(Date.parse(latest.expires_at)) })}</span>
        </p>
      </div>
    );
  })();

  const ledger = (
    <div className="history-grid">
      {latestObject}
      <div>
        <ul className="ledger plate" aria-label={t("account.listLabel")}>
          {rows.map((row) => {
            const at = issued(row);
            const band = row.band ? t(`result.bands.${row.band}`) : undefined;
            const date = "date-" + row.id;
            return (
              <li key={row.id}>
                {row.mode === "deep" ? (
                  <ThumbPass index={row.index} heats={heatsFor(row, 8)} glyph={tonightGlyph(at)} />
                ) : (
                  <ThumbFlyer index={row.index} band={band} />
                )}
                <div className="l-main">
                  <span className="l-date" id={date}>
                    {formatDate(at)} · {t(row.mode === "deep" ? "account.guestPass" : "account.handStamp")}
                  </span>
                  <b>
                    {row.index ?? "–"}
                    <small>/100</small>
                  </b>
                  <span>
                    {[band, row.interval && `${row.interval.low}–${row.interval.high}`, t("home.count", { n: row.word_count })]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </div>
                <div className="l-act">
                  <button type="button" className="btn" disabled={busy} onClick={() => open(row)}>
                    {t("account.open")}
                    <Icon name="arrow" />
                  </button>
                  <button
                    type="button"
                    className="icon-btn"
                    disabled={busy}
                    aria-label={t("account.remove")}
                    aria-describedby={date}
                    onClick={() => setPending({ action: "delete", id: row.id })}
                  >
                    <Icon name="trash" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
        {data?.more && (
          <div className="ledger-foot">
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() =>
                void perform(async () => {
                  const next = await list(rows.at(-1));
                  setData({ ...next, rows: [...rows, ...(next.rows ?? [])] });
                })
              }
            >
              {t("account.more")}
            </button>
          </div>
        )}
      </div>
    </div>
  );

  const detailView = detail && (
    <>
      <div className="detail-top">
        <button type="button" className="btn btn-quiet" onClick={() => setDetail(undefined)}>
          <Icon name="back" />
          {t("account.close")}
        </button>
      </div>
      <ResultHero
        result={detail.result}
        mode={detail.row.mode}
        at={issued(detail.row)}
        id={detail.id}
        level={2}
        onPanel={openPanel}
      />
      <HouseRule className="result-rule" />
      <Flags result={detail.result} />
      {detail.text && detail.result.sentences?.length ? (
        <SentenceHeatmap text={detail.text} sentences={detail.result.sentences} streaming={false} />
      ) : null}
      {detail.row.mode === "deep" ? (
        <>
          <LensPanel result={detail.result} mode="deep" />
          <Signals result={detail.result} />
        </>
      ) : (
        <>
          <Signals result={detail.result} />
          <LensPanel result={detail.result} mode="quick" />
        </>
      )}
      {detail.text ? (
        <details className="saved-essay">
          <summary>{t(detail.local ? "account.local" : "account.text")}</summary>
          <p className="saved-text">{detail.text}</p>
        </details>
      ) : (
        <p className="no-text">{t("account.noText")}</p>
      )}
      <KitSection>
        <EvidenceKit
          result={detail.result}
          mode={detail.row.mode}
          version={detail.row.engine_version}
          date={issued(detail.row)}
        />
      </KitSection>
    </>
  );

  return (
    <div data-mode={detail?.row.mode ?? latest?.mode ?? "deep"}>
      <div className="history-head">
        <div>
          <span className="eyebrow">{t("account.eyebrow")}</span>
          <h1>{t("account.title")}</h1>
        </div>
        <p>{t(data?.owner ? "account.retention" : "account.intro")}</p>
      </div>
      {message && (
        <p role="status" className="notice history-notice">
          {t(message)}
        </p>
      )}
      {!data ? (
        <p>{t("account.loading")}</p>
      ) : !data.owner ? (
        signIn
      ) : (
        <>
          {detail ? detailView : rows.length ? ledger : <p className="account-card plate">{t("account.empty")}</p>}
          <div className="ledger-foot account-actions">
            <button
              type="button"
              className="btn btn-quiet"
              disabled={busy}
              onClick={() =>
                void perform(async () => {
                  await action({ action: "signOut" });
                  setDetail(undefined);
                  setPending(undefined);
                  setDevice([]);
                  setData({ owner: null });
                })
              }
            >
              {t("account.signOut")}
            </button>
            {(["deleteAll", "deleteAccount"] as const).map((k) => (
              <button
                type="button"
                key={k}
                className="btn btn-quiet"
                disabled={busy}
                onClick={() => setPending({ action: k })}
              >
                <Icon name="trash" />
                {t(k === "deleteAll" ? "account.all" : "account.account")}
              </button>
            ))}
          </div>
          {pending && (
            <div className="confirm" aria-live="polite">
              <p>
                {t(
                  {
                    delete: "account.confirmOne",
                    deleteAll: "account.confirmAll",
                    deleteAccount: "account.confirmAccount",
                  }[pending.action],
                )}
              </p>
              <div className="account-actions">
                <button type="button" className="btn btn-primary" disabled={busy} onClick={() => remove(pending)}>
                  {t("account.confirm")}
                </button>
                <button type="button" className="btn btn-quiet" disabled={busy} onClick={() => setPending(undefined)}>
                  {t("account.cancel")}
                </button>
              </div>
            </div>
          )}
        </>
      )}
      <InfoDialog panel={panel} dialog={dialog} />
    </div>
  );
}
