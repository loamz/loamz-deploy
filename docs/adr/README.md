> **The family's decisions live here, once.** Nine records below were written before the repositories were split and were copied into loamz-agents and loamz-data; those copies are
> deleted (2 November 2026). Some predate the Loamz names and the cell model; where they disagree with [../ARCHITECTURE.md](../ARCHITECTURE.md), that page wins.

# Architecture Decision Records

An ADR records one architectural decision: the context, the choice, and its consequences. Write one when a change
alters a boundary between packages, a public contract, a storage or runtime model, or anything that would be costly
to reverse. Small, local choices do not need one.

## Process

1. Copy the template below to `NNNN-short-title.md` (next free number, kebab-case title).
2. Set status to `proposed` and open a PR (`docs(adr): ...`). Discussion happens on the PR.
3. On merge the status becomes `accepted`. Add a row to the index below.
4. ADRs are immutable once accepted. To change a decision, write a new ADR and mark the old one
   `superseded by NNNN`.

## Template (MADR)

```markdown
# NNNN. Title of the decision

- Status: proposed | accepted | deprecated | superseded by [NNNN](NNNN-title.md)
- Date: YYYY-MM-DD
- Deciders: @handle

## Context and problem statement

What forces are at play? What problem are we solving?

## Decision drivers

- Driver 1
- Driver 2

## Considered options

- Option A
- Option B

## Decision outcome

Chosen option: "Option A", because ...

### Consequences

- Good: ...
- Bad: ...

## Pros and cons of the options

### Option A

- Good: ...
- Bad: ...

### Option B

- Good: ...
- Bad: ...
```

## Index

| ADR | Title | Status | Date |
| --- | --- | --- | --- |
|  |  |  |  |
