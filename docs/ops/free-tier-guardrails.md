# Free-tier guardrails: how we never get a surprise bill

**Rule:** we run on the *Always Free* allowances only. The Oracle account is "Pay As You Go" (that is what let us get the machine),
which means **anything above the free allowance is billed without a warning**. So every cloud thing is checked against a limit
before it exists, watched while it runs, and capped in code where we can.

*Numbers below are what Oracle, Cloudflare and Backblaze publish, as we last confirmed them (2026-10-26). Sources disagree in a few
places (marked "confirm"). Always check the provider's own page before relying on a number.*

## 1. What we use, and its ceiling

| Provider and item | Free allowance | What we use now | Hard stop |
|---|---|---|---|
| Oracle Arm machines (A1) | Oracle's page (2026-10-27): 1,500 OCPU-hours and 9,000 GB-hours a month, i.e. 2 cores and 12 GB; older accounts may still have 4 cores and 24 GB | 1 machine, resized on 2026-10-27 to 2 cores and 12 GB: **exactly the published allowance**. It used about 1.1 GB of memory after the resize. Do not grow it. | `scripts/oci-free-check.sh` fails if a second Arm machine appears. **We cannot add any Arm machine.** |
| Oracle disks (boot plus block) | 200 GB in total (confirm: some pages say 100 GB for block) | 100 GB boot, no block volume | The check script warns above 100 GB and fails above 200 GB |
| Oracle volume backups | 5 | 0 | Script fails above 5 |
| Oracle outbound data | 10 TB a month | tiny | Watch Cost Analysis |
| Oracle Object Storage | 20 GB in total (confirm: 10 GB Standard plus 10 GB each Infrequent and Archive on one page) | none yet | Backups to it are capped by the backup job's retention |
| Oracle public IPs | 1 ephemeral per machine free; **an unattached reserved one is billed** | the machine's own | Script fails on any unattached reserved IP |
| Oracle load balancers, NAT gateways, databases, Vault, Logging (10 GB a month) | each has its own free amount | none of the paid ones (a NAT gateway exists but is unused: believed free, confirm on the price list; delete it if nothing uses it) | Script lists them |
| Cloudflare R2 | 10 GB stored, 1 M writes and 10 M reads a month, no egress fee | not yet used (files are on the machine's disk) | **Chat server refuses new files above `CHAT_BLOB_BUDGET_MB`** (below) |
| Cloudflare Pages, Tunnel, Access (50 users), Turnstile, Email Routing, DNS | free plans | DNS and Email Routing | None of these bill when over; they stop or throttle |
| Backblaze B2 | 10 GB | not yet used | Set a **0 dollar cap** in the B2 account page when you create it |
| Resend (email) | about 3,000 emails a month on the free plan | approval and request emails | The free plan stops sending at the limit; it does not bill |
| Domains | not free | loamz.com is already paid | none |

## 2. What the system refuses to do on its own

- **Files:** the chat server stops accepting new photos, voice notes and files once the total reaches `CHAT_BLOB_BUDGET_MB`
  (default 20,000 MB, in `deploy/ansible` as `blob_budget_mb`). People see "Photos and files cannot be sent right now." Messages keep working.
  When the files move to R2 this number must be lowered to **8,000** (80% of the 10 GB R2 allowance).
- **Per person:** 200 MB of files a day, 16 MB per file, 20 feedback notes a day, 300 address lookups a day, per-address request limits.
- **Email:** at most one "someone asked to join" email per request and one approval email per person; nothing mass-mails.

## 3. What the owner does once (only the owner can; these are in the Oracle console)

1. **Create a budget that alerts at one dollar.** Console → *Billing & Cost Management → Budgets → Create budget*:
   target "Tenancy", amount **1**, add two alert rules: *Actual spend* at **1%** and *Forecasted spend* at **1%**, both emailing you.
   Anything above zero is then reported the same day.
2. **Look at Cost Analysis** (same menu) after a week: it must show **0**.
3. **Delete the `vm-grabber` user's API key** (the limited user made for the machine hunt) and, if you like, the user. It can create machines; it is no longer needed.
4. **Never click** an "Upgrade", "Add resource" or "Create" button for a service that is not on the "Always Free" list. When in doubt, ask first.
5. **Keep Pay As You Go.** Downgrading would risk the machine being reclaimed as idle; the budget alert above is the protection instead.
6. When you open Backblaze and Cloudflare R2 accounts: in Backblaze set the daily caps to **$0** (*Caps and Alerts*); in Cloudflare R2 keep the bucket on the free plan and add an email alert at 80% of 10 GB.

## 4. The weekly check (5 minutes)

```bash
scripts/oci-free-check.sh        # exit 0 and "inside the Always Free allowance" is what you want
```
Then glance at: Oracle *Cost Analysis* (0), Cloudflare R2 storage (under 8 GB), Resend usage (under 2,000 this month), and the VM's disk
(`df -h /` on the machine, under 70%). If anything is off, stop adding things and tell Claude.

## 5. Rules for building (for every worker)

- **No new paid resource** (machine, disk, database, load balancer, IP, bucket tier, SMS, paid model) without the owner's written yes. A "free trial" is paid.
- **No scripts that create cloud resources in a loop.** The machine-hunting script is the only one we ever had; it stopped when it succeeded.
- **Everything that grows has a cap in code or in config** (files, logs, backups, emails). New features say what their ceiling is.
- **Model calls** (agents) are budgeted per person and per organization before they ship; free-tier models only for personal use, as the roadmap says.
- **If the account is ever suspended or billed,** the runbooks in `docs/runbooks/` rebuild the service elsewhere from Ansible and backups.
