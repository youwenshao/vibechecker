# Phase 2 beta verification

The beta uses the Phase 1.1 incumbent `deep-qwen7b-q4-p512-v4` (SHA-256 `aeafbb70201caec3029b24799faedd8fee89aacf5ef1bdf09e1eee2673b82d9b`). A Deep service advertising this version verifies its artifact before serving. The original calibration and hardware gates still govern release eligibility. [Phase 1.1 decision](../../eval/reports/phase-1/phase-1.1/report.md)

## Detector lenses

The engine reuses the existing signals. Quick supports four document lenses. Deep adds a Turnitin-style estimate of the share of words in flagged sentences. The web app reads earlier results and explains when a lens is unavailable. [Lens parameters](../../engine/lenses/v1.yaml) · [Fit and holdout counts, sources and input hashes](../../eval/reports/phase-2/lenses.json)

| Lens | Calibration sample | Held-out result | Interpretation |
| --- | ---: | ---: | --- |
| Turnitin-style | 3,651 sentences from 160 human essays | 205 / 3,695 (5.55%) across 138 other essays | Within two points of the plan’s 4% sentence target on essays |
| GPTZero-style | 334 second-language essays | 1 / 46 (2.17%) | Within two points of the 1.1% TOEFL reference. The local essays are longer. |
| ZeroGPT-style | 585 human essays | 23 / 138 (16.67%) | Within two points of the independent benchmark’s 18.4% |
| Grammarly-style | 585 human essays | 30 / 138 in upper band | Local descriptive band. Published numerical target unavailable. |
| VeriGuide-style | 585 human essays | 25 / 138 in upper band | Local descriptive band with the least public evidence. |

The sentence lens uses a cutoff of 0.493956. We selected the first 160 calibration essays in normalized hash order and reserved all 138 eligible validation essays before running the frozen model. Both partitions excluded the mixed-genre trace documents. The reference contains only numeric sentence scores and a hash of the reserved membership. [Evaluation plan](phase-2.md) · [M6 sentence reference](../../eval/reports/phase-2/essay-sentences.json.gz)

The same cutoff flagged 413 / 4,088 (10.10%) human sentences in the original mixed-genre trace and 436 / 6,965 (6.26%) in the prospective trace. Both fell outside tolerance. Earlier attempts at broad calibration also missed. The CUDA half-split gave 46 / 2,345 (1.96%). A cutoff fitted to the original M6 trace gave 127 / 6,965 (1.82%) on its prospective counterpart.

Turnitin describes its 4% as the share of all highlighted sentences that were human. On the prospective mixed-genre trace, people wrote 436 of the 2,408 sentences highlighted by the shipped lens (18.11%). The earlier broad cutoff gave 127 / 1,782 (7.13%) on this separate measure. The methodology page explains the two denominators. [Turnitin’s explanation](https://in.turnitin.com/blog/understanding-the-false-positive-rate-for-sentences-of-our-ai-writing-detection-capability)

The document lenses use the Phase 1 feature cache’s calibration and validation roles. Only registered, labelled human essay rows enter the reference distributions. For the two qualitative lenses, the cutoffs divide the calibration distribution into thirds. These measurements do not establish agreement with proprietary tools on individual essays.

To reproduce with the Phase 1.1 research files, run from the repository root. Add `--enforce` to check the numerical essay operating points. The mixed-genre replays are reported separately.

```sh
uv run vibechecker-eval fit-lenses \
  --features "$research/calibration-v2/stack.sqlite" \
  --historical "$research/deep-qwen7b-q4-p512-v4.test.metal.json" \
  --prospective "$research/calibration-v4-academic/deep-qwen7b-q4-p512-v4.prospective.metal.json" \
  --cache "$corpus_cache" --out eval/reports/phase-2/lenses.json
```

To regenerate the bundled sentence reference, run `python -m vibechecker_eval.lens_sentences` on Metal with the same feature-cache, trace and corpus arguments and `--out <directory>`. Use the Phase 1.1 service’s checkpoint environment. This writes the reserved membership first, then the compressed reference. Pass the latter to the fitter with `--essay-sentences`.

## Verification

- On the M6, 111 Python tests passed with the hardware dependencies. Quick and Deep both scored a registered 480-word ASAP essay. The Deep index of 0 and all 28 sentence scores and UTF-16 offsets matched the frozen historical trace exactly. Document hash `5fc11a68bbf60956d620b43f817cccc26db72e12a9311d7b911e2e273bf72045`.
- `pnpm verify` checked schema drift, TypeScript and 15 web unit tests. All 18 production-build Playwright scenarios passed. They cover the account lifecycle, Turnstile and PKCE redirects, both PDF languages, policy navigation, lens masking, keyboard access, axe and reduced motion. Identity, email delivery, storage and inference endpoints in the browser suite use loopback fixtures.
- All migrations ran on isolated Supabase Postgres 17. The prior SQL suites and 24 pgTAP assertions passed. They cover profile creation, owner visibility, claims, quotas, encrypted-copy access, expiry, deletion and numeric-only feature storage.
- The browser generated A4 PDFs using the eight-signal Deep fixture in both locales. The zh-HK download loads a locally bundled subset of Noto Sans HK. The PDF omits the essay.
- A local backup drill encrypted a real Postgres dump with a disposable OpenPGP key and restored it into a second migrated database. The restored account and profile matched the source. The expiry check removed the 14-day-old fixture and preserved newer and unrelated objects.
- On Windows, 98 Python tests passed and one platform-specific test module was skipped. The M6 run exercised the hardware dependencies.

## Deployment settings

Apply the new migration before switching the application. The inference service needs the existing Quick checkpoints, v4 joblib, Qwen pair and prefill 512. Set the same engine version on the web app and inference service. Both the primary and fallback require the Phase 2 engine and generated contracts.

Set `APP_ORIGIN` to each deployment’s canonical HTTPS origin. Supply the server-side Supabase publishable key and service role key. Generate a 32-byte random `ESSAY_KEK` and store its base64 encoding only in the web service. Each saved essay has an independent data key. Preserve its wrapping key for the lifetime of the encrypted rows. [Web environment settings](../../apps/web/.env.example)

For hosted Supabase Auth, set the site URL and allow the application’s `/api/auth/callback` URL including the locale and optional PKCE flow query. Enable Turnstile for email sign-in, configure the Google client and its Supabase callback, and configure the auth email sender. Google initiation also verifies Turnstile on the application server. The checked-in Supabase configuration uses local development URLs and environment-backed secrets.

Set the client and server Sentry DSNs to enable error reporting. For the nightly export, configure the workflow’s Supabase and R2 secrets, the private bucket name and `FEATURE_EXPORT_ENABLED=true`. Restrict bucket credentials to the archive bucket. Expiry uses each partition’s UTC date and a 12-calendar-month window. [Archive workflow](../../.github/workflows/export-features.yml)

For nightly backups, set `BACKUP_DATABASE_URL` to a TLS PostgreSQL session connection with read access to the application tables and auth users and identities. Configure the backup bucket, its own scoped R2 credentials and an ASCII-armored OpenPGP public encryption key. Keep the private key offline. Enable the schedule with `BACKUP_ENABLED=true`. Configure the bucket’s `database/` prefix to expire at 14 days as a backstop if scheduling stops. The workflow also prunes by UTC date. To verify an offline restore, apply the same migrations to an empty isolated database, then pipe `gpg --decrypt backup.dump.gpg` to `pg_restore --data-only --disable-triggers --single-transaction --exit-on-error --dbname="$RESTORE_DATABASE_URL"` with a privileged restore role. The separately stored `ESSAY_KEK` is needed to read opt-in essays afterward. [Backup workflow](../../.github/workflows/backup.yml)

Live provider delivery, hosted configuration and the operator’s zh-HK editorial review remain staging sign-off items. The changes in this branch do not authorize a public detector release.
