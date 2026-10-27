# Plan: finishing the dots (written 2026-10-27)

Goal: everything already built is connected, safe, backed up and documented; then the stock-model pipeline. Order is by dependency. Owner = you, C = Claude, A = Antigravity, X = Codex.

## Phase 1: make what exists solid (about 1 week)
| # | Item | Who | Done when |
|---|---|---|---|
| 1 | Close the consent gap: agents can only be added through the consent flow (engine rule, not screen rule) | C | adding an agent by email through New chat or Add person is refused with a clear message; test |
| 2 | Backups: daily to B2, monthly to Oracle Archive, local 14 days; R2 holds no backups; restore tested from each | Owner (accounts) then C | one restore passes from each copy; key copied with `backup-secrets.yml` |
| 3 | `/data` block volume (about 100 GB); move Postgres and file storage on it; weekly volume backup | C (owner attaches in console) | VM rebuild keeps data |
| 4 | Media on R2 with short-lived links for chat members only | C | photo and voice e2e pass; non-member gets 403 |
| 5 | Oracle Billing check, alarms (disk 85%, memory 85%), uptime checker and status page | Owner + C | alert email arrives on a test |
| 6 | Real-device pass on Android and iPhone: install, push, mic, keyboard, rail | Owner + A | checklist green, bugs filed |

## Phase 2: agents become useful (about 1 to 2 weeks)
| # | Item | Who | Done when |
|---|---|---|---|
| 7 | Marketplace connected to the server (X18): installs, on/off, permissions are real | C (or X) | turning a skill off changes what Helper can do; test |
| 8 | Assistant tools per installs: web research, files | C | an installed tool is used, a blocked one never |
| 9 | Google connectors (Drive, Gmail, Calendar) via OAuth | Owner (Google Cloud client) then C | a person connects an account and Helper reads a file; consent shows recipients |
| 10 | Agent directory endpoint and usage numbers in the Agents tab | C | picker lists real agents; ring shows real usage |
| 11 | Focused UI passes: chat pane, bubbles, composer, list; small screens | A + C review | WhatsApp-style comparison list closed |
| 12 | CI: design-sync check and browser scripts in GitHub Actions; fix flaky safety script | C | green on a clean clone |

## Phase 3: the stock-model pipeline (about 2 to 3 weeks, after owner answers)
Decisions needed first: model type and size, prediction target, run frequency, live data source.
| # | Item | Who | Done when |
|---|---|---|---|
| 13 | Model package spec (model, feature code, window, frequency, version, metrics) | C | written and agreed |
| 14 | Model registry in loamz-data | C/X | upload, list, read spec |
| 15 | Inference service (CPU, ONNX or trees) with memory cap | C | predicts a window in under 1 s on the VM |
| 16 | Window fetcher for the chosen data source, with rate limits and caching | C | exact window returned and cached |
| 17 | Agent tools `get_model_spec`, `fetch_window`, `predict`; schedule template | C | an agent runs the model on a schedule and posts results |
| 18 | Publish command on the local server (train, backtest, package, upload) | Owner + C | one real model served end to end |
| 19 | Monitoring: predictions compared with outcomes, drift and stale-model alerts | C | alert fires in a test |
| 20 | Local server backup: encrypted weekly sync of raw and silver to B2 or InterServer 1 slice | Owner (account) + C | restore of a sample passes |

## Phase 4: before real users (ongoing)
Legal blanks and `LEGAL=on` (owner); Android signing key and APK (owner + X); Resend verified (owner); invite 10 to 20 people and read feedback; archive `loamz-server`; offline SQLite store spike; spare VPS decision when measurements show pressure (4 GB headroom is the trigger).

## Spare VPS rule
Buy only when memory stays above 85% or inference jobs slow chat. First choice: InterServer 4 slices ($12/month). Data and agents already assume separate machines, so moving the data platform or inference there is a deploy change, not a rewrite.

## Owner checklist (accounts and decisions)
1. Backblaze B2 account, bucket and key. 2. Oracle: Archive bucket, attach `/data` volume, check Billing. 3. Resend domain verification. 4. Google Cloud OAuth client. 5. Answer the four model questions. 6. Legal blanks. 7. Android signing key. 8. Try the app on real phones.
