# The Loamz family: how products fit together

*Written 2 November 2026. This page is the one place that says what the products are, who may depend on whom, and what is checked by a
test rather than by memory. The plan that drives it is the owner's: adding product N should cost one new repository and one file
(`products/<id>.yml`, not written yet), and no change to the other products.*

## The pieces

| Role | Repositories | What it is |
|---|---|---|
| **Engines** | `loamz-chat` (Rust), `loamz-agents` (Python), `loamz-data` (Rust) | The servers, each with its own web app. They talk to each other only through public, versioned APIs. |
| **Clients** | `loamz-python`, `loamz-rs` | Thin public SDKs. Solutions are built on them as a library on top of the engines. They are not engines and hold no server code. `loamz-rs` is a placeholder until a Rust solution needs it. |
| **Solutions** | `loamz-solutions` | Apps built on the engines through the SDKs; it offers tools to Agents over MCP. |
| **UI kit** | `loamz-ui` (not made yet) | The design system, browser sign-in, later the conversation UI, as versioned packages. Today the design system is copied by script from `loamz-chat`. |
| **Control plane** | `loamz-platform` (being rebuilt) | Provisioning, plans, entitlements, usage, billing. Never in a request path. |
| **Infrastructure** | `loamz-deploy` (this repository) | Ansible, Keycloak, Caddy, backups, runbooks, and (planned) the product registry. |

One Keycloak realm, `loamz`, signs everyone in. A Keycloak **organization is a tenant**. Each product is one Keycloak client with one audience.

## The rules

| # | Rule | Checked by | Today |
|---|---|---|---|
| R1 | Products call each other only through their public, versioned `/api/v1`; the spec is checked in and a drift test keeps it true. | `make spec` plus `git diff --exit-code` in each producer; a pinned copy and hash in each consumer | Data has the spec and a test; Agents' spec is stale; none of this runs in CI everywhere |
| R2 | Allowed edges: Platform to the engines (provision, entitle, usage, erase); Agents to Data; Agents to registered tool servers; Chat to Agents; Solutions to the SDKs. **Data depends on nothing.** Nothing depends on Platform or Solutions. | Data: `server/server/tests/layering.rs`. Agents: import-linter. Web apps: dependency-cruiser | **Data: enforced.** The rest: planned |
| R3 | One realm; one client and one audience per product. A call from one product to another is an RFC 8693 token exchange for the callee's audience. A user's token is never forwarded. | The product registry validator; a family smoke test | Works for Agents to Data (client `loamz-agents`, audience `loamz-data`); not checked |
| R4 | A tenant is a Keycloak organization alias. Each product offers idempotent provision, entitlements, usage and erase. No product reads another's database. | Contract tests per adapter | Agents has entitlement and erase endpoints; Data has `POST /api/v1/orgs/{org}/account` |
| R5 | A product that agents may use ships an MCP server and a tools manifest, and is listed in the registry. | Registry validator | Not built: first-party tools are hard-coded in Agents |
| R6 | Web apps depend on `@loamz/*` packages by exact version. No app imports another app. | CI: no `src/design` copy | Not yet: three copies of the design system |
| R7 | One product tells another by a signed, idempotent webhook from an outbox. | A consumer test | Not built |
| R8 | **Clients stay thin.** The SDKs are written from each engine's checked-in API description, carry the API's version, hold no server code and no engines. Server conventions (token claims, problem documents, stream frames) are a written spec plus test vectors that each engine runs, not shared code. | `.importlinter` and a dependency guard in the SDK repos; vectors in each engine's tests | Partly: `.importlinter` exists; the vectors and the guard do not |
| R9 | Each repository enforces its own edges in CI. | The above | Data yes; others no |

## Why shared code is not shared code

The engines are written in two languages, and the SDKs are for people outside. So the three token verifiers (Rust in Chat and Data,
Python in Agents) stay separate and agree through **written conventions and conformance vectors**, a set of signed example tokens and
expected outcomes that every engine's tests must pass. A shared Rust crate for Chat and Data is worth making only when a third Rust
service needs it, or a security fix lands in one copy and the vectors show the other lagging twice. It would live in its own private repository,
never in an SDK.

## Adding a product (the goal, and what is missing)

Today a new product reaches Agents by changing five or six repositories (the Agents catalog and builders, the Keycloak realm template and
`settle.py`, an icon in Chat, a block of settings here, then lock bumps). The goal is: a new repository, plus `products/<id>.yml` here.
That needs the registry and its validator, one reconciler for Keycloak clients, a registry-driven Agents tool list, a generic deploy role, and a
control plane that reads the same file. The order, and why, is in the plan the owner approved on 2 November 2026
(`~/.claude/plans/i-want-to-build-eager-dusk.md` on the owner's machine).

## What is true of the live system

One Oracle Always Free machine (2 cores, 12 GB) runs Postgres, Keycloak, Chat, Agents, the chat bridges and Caddy. Data is not deployed.
There is no staging, no alerting that anyone has set up, and no restore that has been tried end to end (see `docs/runbooks/`). Every product
added to that machine multiplies those gaps, which is why the first phase of the plan is about them.
