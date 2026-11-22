# RFC-006 · Privacy and retention

Submitting an essay authorizes in-memory scoring. IndexedDB holds the text on the submitting device for up to 30 days and clears stale entries when accessed. The server stores a result with numeric signals, sentence offsets and flags. An anonymous result has a single-use claim secret. The server stores its keyed hash and consumes it atomically when a verified user claims the result.

Saving the essay on the server requires a signed-in account and an explicit choice on that submission. Each essay has a random AES-256-GCM data key. The web server wraps the key under the separate environment-held key and authenticates the owner and check ID on both encryption operations. Database reads enforce ownership and expiry. Deleting the check or account cascades to the encrypted copy.

| Record | Lifetime | Enforcement |
| --- | --- | --- |
| Result, encrypted essay and result cache | 30 days | Expiry filters and scheduled database cleanup |
| Daily quota usage and de-identified feature rows | 7 days | Scheduled database cleanup |
| Numerical feature archives | 12 calendar months | Nightly R2 export and prune |
| Encrypted database backups | 14 days | Nightly prune and bucket expiry rule |

The feature archive contains the mode, engine version and numeric signal values. Application telemetry rebuilds errors from an allowlist of operation and category names. The privacy pages in English and zh-HK explain processors, transfers, retention and access and correction requests. [Schema and policies](../../supabase/migrations/20261122011808_phase_two_accounts.sql) · [Operations and verification](../plans/phase-2-evidence.md)
