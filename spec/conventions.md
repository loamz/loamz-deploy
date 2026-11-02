# Conventions every engine follows

*Version 1, 2 November 2026. The engines (Chat, Agents, Data) are written in two languages and share no server code, so they agree on
these rules in writing and prove it with the vectors in `vectors/`. When a rule changes, change this page and the generator, regenerate,
and copy the vector file into each engine's tests (`python3 spec/generate_vectors.py`; `--check` in CI).*

## Tokens

- Signed with **RS256 only**. The algorithm is never taken from the token: `HS256` and `none` are refused.
- The key is looked up by the header's `kid` in the issuer's key set. No `kid` is invalid; an unknown `kid` is a different error
  (`unknown_key`) so a verifier knows to refresh its keys once.
- Required claims: `exp`, `iss`, `aud`, `sub`. The issuer must equal the configured issuer, and `aud` must contain the product's own audience (`loamz-<product>`).
- `organization` (Keycloak's) is either a list of aliases or an object keyed by alias; either way the caller's organizations are the
  aliases, sorted, without duplicates. A person may have none. `groups` are paths, sorted, without duplicates.
- `loamz_kind` of `agent` or `service` makes the caller a service; anything else is a person.
- `azp` is the client the token was issued to. An `act` claim (`{"sub": ...}`) marks an exchanged token: the caller is the person, the
  actor is `act.sub`. A product may also name clients whose person tokens count as an agent acting (Data: `LOAMZ_DATA_AGENT_CLIENTS`).
- `vectors/token/<audience>.json` holds a key set, signed tokens and the outcome each must give. Times are 2001 and 2100, so no clock is needed.

## Still to write (each needs vectors before it is a rule)

Problem documents (RFC 9457, and Data's "404, never 403"), the event-stream frames Agents sends and Chat reads, pagination and
idempotency, the tenant lifecycle calls (provision, entitlements, usage, erase), and the webhook signature.
