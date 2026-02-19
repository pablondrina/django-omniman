# Philosophy: SIREL

Omniman follows the **SIREL** philosophy—three pillars that guide every decision:

| Pillar | Filter Question |
|--------|-----------------|
| **Simple** | Can this be done in a simpler way? Am I adding unnecessary complexity? |
| **Robust** | What if this runs twice? What if data is stale? Does it handle failures? |
| **Elegant** | Is the API intuitive? Is the code readable? Does it follow Django patterns? |

> **SIREL is not an acronym**—these are three words that summarize the project philosophy.

---

## Core vs Implementation

Understanding what belongs in Omniman Core vs what belongs in your implementation is crucial.

### What is CORE (Kernel)?

| Belongs to Core | Examples |
|-----------------|----------|
| Essential models | `Channel`, `Session`, `Order`, `Directive`, `IdempotencyKey` |
| Services | `ModifyService`, `CommitService`, `SessionWriteService`, `ResolveService` |
| Protocols | `Validator`, `Modifier`, `DirectiveHandler`, `IssueResolver` |
| Registry | Extensibility system |
| Invariants | The 14 inviolable rules |

### What is IMPLEMENTATION?

| Not Core | Examples |
|----------|----------|
| Admin/UI | Unfold templates, badges, navigation |
| API/DRF | Endpoints, serializers, viewsets |
| Integrations | iFood, WhatsApp, Rappi |
| Terminology | "Cart" vs "Order" vs "Draft" |
| Status flow | Tabs, filters, visual transitions |

### The Golden Rule

> **If it's only for UX/integration** → Implementation
> **If it's a consistency/auditability/commit contract** → Core

---

## Design Principles (P1-P5)

### P1 — Small, Opinionated Kernel

Few tables, few invariants. Power comes from contracts and extensions, not model proliferation.

### P2 — Validators and Modifiers (Strict Separation)

- **Validators**: Binary gates (pass/fail). They do not mutate state. They do not perform IO.
- **Modifiers**: Deterministic, idempotent transformations. They do not perform IO.
  - Modifiers **do not fail for missing data**; they perform no-op when needed.
  - They may only fail for internal inconsistency (e.g., negative total).

### P3 — Auditability First

Everything relevant is recorded in `OrderEvent`. Price overrides require an event.

### P4 — Conservative Eventual Consistency

Side effects (stock, payment, etc.) happen via **Directives** (at-least-once). Failures degrade conservatively.

### P5 — PostgreSQL First-Class with Guardrails

PostgreSQL is the officially supported database. Compat mode (SQLite) is experimental and blocked in production by default.

---

## Decision Checklist

Use this checklist BEFORE implementing any change:

### 1. SIREL Alignment

- [ ] **Simple**: Is this the simplest way to solve it?
- [ ] **Robust**: Is it idempotent? Handles failures? Stale-safe?
- [ ] **Elegant**: Follows Django patterns? Intuitive API? Readable code?

### 2. Invariant Verification

- [ ] Does not violate any of the 14 invariants (I1-I14)?
- [ ] Handlers are idempotent?
- [ ] Validators don't perform IO?
- [ ] Modifiers don't perform IO?

### 3. Correct Location

- [ ] Is it Core or Implementation? Is it in the right place?
- [ ] If Core: does it contribute to consistency/auditability?
- [ ] If Implementation: does it depend only on Core's public APIs?

### 4. Extensibility

- [ ] Uses Registry/Protocols instead of rigid inheritance?
- [ ] Allows customization without forking?

---

## Anti-Patterns (What NEVER to Do)

### In the Kernel

| Anti-Pattern | Why? |
|--------------|------|
| Add external lib dependency (django-money, etc) | Kernel must be minimal |
| Assume specific UI (Unfold, React, etc) | Kernel is headless |
| Perform IO in Validators or Modifiers | Breaks purity and testability |
| Create per-item state machine | State is derived from checks/issues |
| Ignore `expected_rev` in write-backs | Opens race condition vulnerabilities |
| Commit without `idempotency_key` in production | Allows Order duplication |

### In Implementation

| Anti-Pattern | Why? |
|--------------|------|
| Access models directly without Services | Skips validations and hooks |
| Modify Session without `ModifyService` | Doesn't increment `rev`, doesn't invalidate checks |
| Write checks without `SessionWriteService` | Not stale-safe |
| Ignore `Channel.config` | Each channel can have different rules |
| Hardcode status/terminology | Use `Channel.config.terminology` |

---

## Recommended Patterns

### For New Features

1. **Define the Contract First** (Spec-Driven)
   - Write the Protocol or interface before code
   - Document expected invariants

2. **Implement as Contrib or Example**
   - `omniman/contrib/` for reusable modules
   - `example/` for specific integrations

3. **Register via Registry**
   - Don't use inheritance; use composition via Protocols
   - Register in `apps.py` during `ready()`

### For Existing Modifications

1. Read the current spec
2. Verify affected invariants
3. Maintain backward compatibility
4. Update tests and docs

---

## Canonical Vocabulary

Official project terms—always use these, without synonyms:

| Term | Meaning |
|------|---------|
| **Channel** | Logical origin of the order |
| **Session** | Mutable pre-commit unit |
| **handle_type / handle_ref** | Resume/uniqueness handle (get-or-open). Not "owner", it's a context identifier |
| **Commit** | Session → Order (idempotent) |
| **Order** | Canonical order (sealed) |
| **OrderEvent** | Append-only audit log |
| **Directive** | Pending operational directive (at-least-once) |
| **IdempotencyKey** | Dedupe/replay guard |
| **Checks** | Async check results (by `code`) |
| **Issues** | Detected problems, with actionable actions |
| **Actions** | Executable corrections (always with `ops[]`) |
| **Freshness** | `check.rev == session.rev` |

> Deprecated terms: "Effects", "Outbox", "OutboxMessage" → use **Directive**
