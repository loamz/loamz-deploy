# Deployment plan (free tier first)

Status: proposal, not built. Free-tier figures come from third-party write-ups in mid-2026 and **must be checked on each
provider's own page before relying on them**; they change without notice.

## What the 100 GB can and cannot be

| Need | Free option | Verdict |
|---|---|---|
| Disk for Postgres and local files | Oracle Always Free: 200 GB of block storage, shared by boot and data volumes (a boot volume is at least ~47 GB) | Yes: this is the "100 GB" that works |
| Object storage (S3 API) | Cloudflare R2: 10 GB, free downloads. Backblaze B2: 10 GB. One vendor advertises 100 GB free (Gozunga) but only on its own marketing page | No: about 10 GB per provider |
| Playbook.com Free (a creative-asset manager, not an object store) | "100GB storage or up to 300 assets", 1,000 API calls a month, 5 public share links, no CDN links | **No for the app** (see below) |
| Compute | Oracle Always Free Ampere (ARM). **Reported to have been cut in June 2026 from 4 CPUs / 24 GB to 2 CPUs / 12 GB, inconsistently enforced** | Enough for this app either way |

So: Postgres and, at first, encrypted media on the 200 GB disk; R2 or B2 only for off-site backups and later overflow.

## Playbook.com (checked against their pricing page)

Free plan: 100 GB **or 300 files, whichever comes first**, 1,000 API calls a month, 2 GB per video, 5 public share links,
no CDN links, no S3-compatible access. It is built for design teams sharing assets, and its terms say nothing about use as
storage behind another app.

- **Not usable for chat media.** Every encrypted photo or voice note is a file: 300 files is gone on day one. 1,000 API
  calls a month is about 33 a day, and each upload or download costs at least one call.
- **Possible, but not worth it, for backups.** One encrypted database dump a day fits 300 files and 1,000 calls, but we
  would be leaning on a product not meant for it, with no promise of keeping the account. Cloudflare R2 or Backblaze B2
  (10 GB each, made for this, S3-compatible) are the safer homes for dumps, and a database dump is far below 10 GB.
- **Where 100 GB does exist for free:** Oracle's 200 GB disk on the VM. Use that for media.

## Without Oracle: what is left (checked October 2026; verify on each provider's page)

**Neon (managed Postgres), free plan:** about 1 GB per project (recently doubled from 0.5 GB), **100 compute-hours a month**,
and the database sleeps after 5 minutes idle, which the free plan cannot turn off. When the monthly hours run out, compute
is suspended until the next cycle. A chat is used around the clock, so it would be awake far more than 100 hours (730 in a
month), and every wake-up after idle adds a delay to the first message. Our server also holds one permanent connection
for change notifications, which would keep it awake all the time. Neon is fine for development or a tiny alpha; not for a
live messenger. **Supabase free** pauses a project after a week idle, has 500 MB and no backups.

**Hosting the Rust server for free:** I found no free host that keeps a container running 24/7. Fly.io has no free tier;
Render's free service sleeps after 15 minutes and takes 30-50 seconds to wake (which would break live delivery); Google Cloud
Run scales to zero and I could not confirm how open connections are billed. The realistic choices are:

| Option | Cost | Always on | Notes |
|---|---|---|---|
| Small VPS running the current server and Postgres | about $4-6 a month | yes | Least work. Everything we built runs unchanged, with real Postgres |
| Cloudflare-native (Option B below) | $0 for an alpha, $5 a month when it grows | yes | A port of the server layer; no database to host, no VM |
| Neon plus a free host | $0 | no | Sleeps and runs out of hours; not recommended |

## Option B: Cloudflare-native (Pages for the app, Workers for the server, R2 for files)

**Fits as is:** the web app on Pages (free, global, HTTPS, single-page fallback for `/auth/callback`; serve the API on the
same domain so the refresh cookie keeps working). Files in R2, uploaded **straight from the browser** with short-lived signed
URLs the server issues after checking membership (Workers cap request bodies, so they must not carry the bytes). R2 lifecycle
rules expire old objects. R2 costs $0.015 per GB-month past the free 10 GB, so **100 GB is about $1.50 a month with free
downloads**: this is also the place for large files and videos.

**Needs a port, not a copy:** the server. It is Rust with axum, sqlx and Postgres `LISTEN/NOTIFY`; none of that runs in a
Worker. The Cloudflare equivalents suit our design well:

- one **Durable Object per conversation** = one writer at a time, which is exactly the epoch check, gap-free numbering and
  safe retries we already enforce; its built-in SQLite holds the log;
- the object holds the live connections (WebSocket), replacing the SSE hub and Postgres notifications;
- accounts, devices, key packages, welcomes, sessions and codes in D1 or a per-account Durable Object;
- our pure crates (`chat-domain`, `chat-identity`, `chat-proto`) compile to WASM and are reused. The `worker` Rust crate
  supports SQLite-backed Durable Objects.

Cost of the port: the server layer (`chat-server`, `chat-store-pg`, about half the Rust code) is rewritten and its tests
re-aimed; the encryption core, the web app and the wire format do not change. Keycloak cannot run on Workers; work sign-in
would verify tokens from an identity provider hosted elsewhere, or wait.

**Free-plan limits to design around (verify on Cloudflare's pages):** Workers 100,000 requests a day and 10 ms CPU per
request; Durable Objects and D1 about 100,000 rows written a day and 5 GB. A message writes several rows (the entry and its
receipts), so the free plan carries a few thousand messages a day: right for an alpha, not for growth. The $5 a month plan
lifts this by orders of magnitude.

**Playbook.com for videos: not recommended** (300-file cap, 1,000 API calls a month, no direct or CDN links on free, not
intended as app storage); saving $1.50 a month is not worth a fragile part.

## How far 100 GB goes

- A message costs the server roughly 0.5 KB (ciphertext, row and index). Each message also causes up to two receipts,
  so call it 1.5 KB. One user sending 40 messages a day: about 22 MB a year. **10,000 users: about 220 GB a year.**
  Fine for a pilot; later, batch or prune receipts and expire delivered entries.
- **Media is what fills disks.** 10,000 users sharing 5 photos a day at 200 KB is about 10 GB a day. So media needs a
  retention rule (delete from the server once delivered to all devices, or after 30 days) and the client must
  compress before encrypting. Without that, 100 GB lasts days, not months.

## Reference setup: one VM, everything in containers

```
Internet -> Caddy (HTTPS, automatic certificates, serves the web app, proxies /api)
              |-> chat-server (Rust)  -> Postgres 16 (same VM, local disk)
              |-> keycloak (optional, work sign-in, ~1 GB RAM)
Nightly: pg_dump -> encrypted with age -> R2 or B2 (off-site)
```
A browser needs HTTPS for the encryption API, the service worker and secure cookies, so **a domain name is required**
(a few dollars a year; Cloudflare's free DNS is fine). The app and the API must share one origin (Caddy does this) so the
refresh cookie (`SameSite=Strict`) keeps working.

ARM note: Oracle's free machines are ARM (aarch64). CI must build the server image for `linux/arm64`; the web bundle is
the same everywhere.

## Ansible: yes, it fits

One VM and a handful of containers is exactly what playbooks are good at. Proposed layout (`deploy/ansible/`):

- `roles/base`: user, SSH hardening, firewall (80/443 only), fail2ban, automatic security updates, swap.
- `roles/docker`: engine and compose.
- `roles/app`: renders `compose.yml` and the environment file from templates; secrets from **ansible-vault**.
- `roles/caddy`: site config with strict CSP and HSTS.
- `roles/backup`: systemd timer for dump, encrypt, upload; plus a monthly **restore test**.
- `roles/monitoring`: uptime check, disk and memory alerts.
- Optional later: Terraform to create the VM itself; playbooks only configure it.

## What must exist before real users (in order)

Status as of 2026-10-26. **Done** means built and tested here; it is not the same as deployed.

**Blockers (nobody should sign in before these):**
1. **Open.** Real SMS. In India, sending OTP texts needs a DLT-registered sender and templates, so a global provider's
   trial is not enough; an India-focused provider may be needed. Costs real money per code. Per-address limits are done
   (below), because SMS abuse is billed to you; per-country limits already existed.
2. **Done.** HTTPS (Caddy, automatic certificates), HSTS, and a strict CSP (scripts from self, `wasm-unsafe-eval` for the
   crypto module), checked by signing in through the production build under that policy. **Open:** the domain itself.
3. **Done in the playbooks.** Secrets are made on the machine and never leave it; `backup-secrets.yml` copies the
   device-authority key to the owner once. **Open:** a rotation drill (clients already accept a list of keys).
4. **Done.** Nightly dump, two weeks kept, optional copy to an rclone remote. **Open:** a restore test on a schedule.
5. **Done.** Hourly tidy of published events, handled-event records, expired sign-ins, old codes and lookup counters.
6. **Mostly done.** Per-address limits (sign-in much tighter than the API; the real address comes from our own proxy only).
   **Open:** a cap on open live streams per account, per-account limits.
7. **Open.** Metrics and alerts. Health check exists at `/healthz`; logs carry no content.
8. **Partly done.** A passphrase-protected backup file brings old messages to a new device. **Open:** automatic backup and the
   planned recovery key / passkey, so a lost phone does not depend on someone having made a file.

**Needed for it to feel like a messenger:**
9. **Done.** Closed-app notifications (signed, empty Web Push wake-ups) and an installable app (manifest, icons, service worker).
10. **Done** for photos, voice notes and files (encrypted in the browser, 16 MiB each, 200 MB per person per day, stored as
    bytes the server cannot read). **Open:** retention and clean-up of old files, video.
11. **Open.** Changing a phone number, deleting an account, exporting data, blocking and reporting.
12. **Open.** Privacy policy and terms, and compliance with India's DPDP Act (consent, deletion, breach notice).

Also built since the first plan: groups with names, replies, emoji reactions, in-app feedback (`/api/v1/feedback`).

**Security items still open from the internal review:** certificate expiry and revocation, key-package draining,
message-size padding, interop vectors and fuzzing, and the independent audit. The beta label stays until then.
New this round, worth a look in the audit: file types are re-labelled to octet-stream unless they are plain pictures or voice
notes (a sender picks the type), push addresses are limited to the real push services (the server calls them), and the
backup file's header is authenticated with its contents.

## Staging of the rollout

1. **Private alpha** (invite only, tens of people): items 1-7 and 9. One VM, no Keycloak.
2. **Pilot**: add 8, 10, 11, work sign-in (Keycloak), a second VM or managed Postgres if the first is busy.
3. **Public**: 12, the audit, status page, support channel.

## Risks to check before committing to Oracle

- Signing up needs a card, and approval is sometimes refused.
- ARM capacity is sometimes "out of stock" in a region.
- I believe idle Always Free machines can be reclaimed; confirm Oracle's current rule.
- The compute cut above. Keep a fallback: a small paid VM (a few dollars a month) or Google Cloud's always-free micro VM (very small).

## Decisions needed from the owner

- Provider: Oracle Always Free, or a small paid VM for reliability?
- A domain name (which?).
- SMS provider and who creates and pays for the account.
- Work sign-in (Keycloak) at launch, or phone only first?
- Who is allowed in at first (invite only?).
