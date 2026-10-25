# Deployment plan (free tier first)

Status: proposal, not built. Free-tier figures come from third-party write-ups in mid-2026 and **must be checked on each
provider's own page before relying on them**; they change without notice.

## What the 100 GB can and cannot be

| Need | Free option | Verdict |
|---|---|---|
| Disk for Postgres and local files | Oracle Always Free: 200 GB of block storage, shared by boot and data volumes (a boot volume is at least ~47 GB) | Yes: this is the "100 GB" that works |
| Object storage (S3 API) | Cloudflare R2: 10 GB, free downloads. Backblaze B2: 10 GB. One vendor advertises 100 GB free (Gozunga) but only on its own marketing page | No: about 10 GB per provider |
| Compute | Oracle Always Free Ampere (ARM). **Reported to have been cut in June 2026 from 4 CPUs / 24 GB to 2 CPUs / 12 GB, inconsistently enforced** | Enough for this app either way |

So: Postgres and, at first, encrypted media on the 200 GB disk; R2 or B2 only for off-site backups and later overflow.

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

**Blockers (nobody should sign in before these):**
1. Real SMS. In India, sending OTP texts needs a DLT-registered sender and templates, so a global provider's trial is
   not enough; an India-focused provider may be needed. Costs real money per code. Per-IP and per-country limits first,
   because SMS abuse is billed to you.
2. HTTPS, domain, HSTS, and a correct CSP for the web app (scripts from self, `wasm-unsafe-eval` for the crypto module).
3. Secrets: the device-authority key certifies every device; losing it invalidates all identities and leaking it lets
   someone forge them. Keep an offline copy, store it in the vault, plan rotation (clients already accept a list of keys).
4. Backups that are tested. The server only holds ciphertext, so its backup is not the problem; see item 8.
5. Cleanup jobs. Today nothing consumes the `outbox` table, so it grows forever; expired sessions, codes, lookups and
   old welcomes also need pruning.
6. Per-IP and per-account request limits, a cap on open live streams per account, and idle timeouts.
7. Health, metrics and logs without content; alerts when the disk, memory or error rate is off.
8. **Chat history backup/recovery.** History lives only in browsers. Clearing site data or losing the phone loses it for
   good (the reset button restores *new* messages only). Needs the planned recovery key / passkey backup before this is
   called a messenger.

**Needed for it to feel like a messenger:**
9. Push notifications when the tab is closed (Web Push, wake-only payload) and an installable app (manifest, service worker).
10. Photos and voice notes (encrypted blobs, quota, retention) - the part that uses storage.
11. Changing a phone number, deleting an account, exporting data, blocking and reporting.
12. Privacy policy and terms, and compliance with India's DPDP Act (consent, deletion, breach notice).

**Security items still open from the internal review:** certificate expiry and revocation, key-package draining,
message-size padding, interop vectors and fuzzing, and the independent audit. The beta label stays until then.

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
