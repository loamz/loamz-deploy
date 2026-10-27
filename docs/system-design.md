# Loamz system design: products, data, and where everything lives

Status: proposal for the owner (2026-10-27). Free tiers first; money only where it clearly buys time or safety.

## 1. What we run (products and their weight)

| Product | Processes | State it keeps | Size now | Grows with |
|---|---|---|---|---|
| Loamz Chat | chat-server, chat-bridge (Rust) | Postgres `chat` (ciphertext log, directory), blobs (photos, voice, files) | 2 MB dump, tiny blobs | people × messages; media dominates |
| Sign-in | Keycloak | Postgres `keycloak` | small | people |
| Loamz Agents | agents server (monolith profile) | Postgres `loamz_agents`, agent workspaces | small | runs, memory |
| Loamz Data | catalog, controller, worker, SeaweedFS (S3), workspace UI | Iceberg tables on S3 (Parquet), Postgres catalog | **empty today** | **stock-market data: the big one** |
| Edge | Caddy | none | | |
| Backups | systemd timer + rclone | encrypted dumps | 2 MB/day | slowly |

Rule: Chat, Sign-in and Agents are small and fit anywhere. **Data decides the disk, the memory and the money.**

## 2. What is free (confirm in each console)

| Resource | Allowance | Notes |
|---|---|---|
| Oracle compute (Arm) | **2 cores, 12 GB total (the owner's account limit)** | one VM uses all of it; there is no second free VM |
| Oracle block storage | **200 GB total, boot disks included** | VM1 boot is 100 GB, so **about 100 GB is left** for a data volume (confirm the 200 GB total in the console) |
| Oracle Object Storage | 20 GB (Standard, Infrequent, Archive combined; sources vary) | Archive: 90-day minimum, slow retrieval |
| Oracle outbound data | 10 TB/month | fine |
| Cloudflare R2 | 10 GB, then $0.015/GB-month, **no download fees** | best place for what people download |
| Backblaze B2 | 10 GB, then $0.006/GB-month | cheapest for cold data |
| GitHub Actions, Resend, Cloudflare Tunnel | free tiers | not storage |

## 3. Sizing the stock-market data (the number we must pin down)

Parquet with compression is about 8 to 15x smaller than CSV. Rough sizes for 5,000 instruments over 20 years:

| Granularity | Rows | Compressed |
|---|---|---|
| Daily bars (OHLCV) | about 25 M | under 1 GB |
| 5-minute bars | about 2 B | about 25 to 40 GB |
| 1-minute bars | about 10 B | about 100 to 150 GB |
| Ticks / order book | tens of billions | far beyond free storage; keep only recent history hot |

So **100 to 200 GB is plausible only if you keep 1-minute bars (or ticks for a short window)**. Daily and 5-minute data fit in the free 100 GB comfortably.

## 4. Storage tiers (the placement rule)

```
 HOT   /data volume on the VM (Oracle block, up to ~100 GB)
       Postgres, SeaweedFS (Iceberg Parquet), last 12-24 months at fine granularity, agent workspaces
       read by DuckDB/Polars at local-disk speed
 WARM  Cloudflare R2   photos/voice/files (E2EE ciphertext), older stock data people query sometimes
       zero download fees, edge delivery
 COLD  Backblaze B2    daily database dumps (second provider), old stock partitions, raw vendor files
       Oracle Archive  monthly database dumps (12 months), final raw archives
```

Data moves down the tiers by age (Iceberg partitions by month; compaction job already exists). Hot never holds more than it needs.

## 5. Compute placement

- There is **one VM: 2 cores, 12 GB, all of it**. Chat, Keycloak, Agents and Postgres use about 3 GB today.
- The data platform must be lean on that box: SeaweedFS plus one query worker (DuckDB/Polars) with a hard memory cap (about 4 to 5 GB), no always-on extras, workspace UI only when needed.
- **Heavy work never runs on the VM:** backfills, ingest, compaction of large tables and sorts run on your own machine (or a paid burst VM for an hour, a few cents), write Parquet, and upload. The VM only serves queries. (An unbounded sort already took down the dev box once.)
- Memory plan: Postgres 2 GB, Keycloak 1.5 GB, Chat and bridge 0.5 GB, Agents 1.5 GB, Caddy 0.1 GB, Data 4.5 GB, headroom about 2 GB. Alarms at 85% memory and disk.
- When this is outgrown, the answer is a small paid VM for Data (a few dollars a month), not squeezing more in.

## 6. Decisions to make (in order)

1. How fine is the stock data (daily, 5-minute, 1-minute, ticks), how many instruments, how many years? This sets the tier sizes above.
2. Accept about $2 to $3 a month once data passes the free tiers (200 GB on B2 is about $1.20, on R2 about $3)? The alternative is dropping fine-grained history.
3. One VM only; heavy ingest runs elsewhere; a small paid Data VM only when measurements say so (recommended).

## 7. Plan after the decisions

1. Attach a 100 GB block volume as `/data`; move Postgres and SeaweedFS onto it; weekly volume backups.
2. Backups: daily to B2, monthly to Oracle Archive, local 14 days; remove backup files from R2.
3. Media to R2 with short-lived links for chat members only.
4. Data platform on the VM against your real stock partitions; measure query times; tune partitioning (symbol group, month).
5. Monitor disk, memory and request counts; alarm before any free limit is hit.
