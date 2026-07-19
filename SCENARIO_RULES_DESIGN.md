# Scenario Rules — Design (validated via brainstorming, 2026-07-19)

Admin UI + rule engine to manually configure positive/negative API outcomes per
airline + route + endpoint, without code changes or redeploys.

---

## 1. Understanding summary

- Covers **all capabilities**: ticketing chain (`search/preOrderVerify/ancillarySearch/order/pay/orderDetail`), pre-issuance baggage, TSY BPI, Standardized BPI.
- Users: internal integration/QA testers; a handful of people, low traffic.
- Today negative cases are hard-coded (`BLOCKED_SECOND_BAGGAGE_ROUTES`, fixed `AIRLINES`); this replaces that with runtime-editable rules.
- Failure shape: **preset per endpoint + optional code/msg override**. Always schema-valid, rendered through the existing envelope helpers.
- Rules are **exact match** (specific airline + origin→destination + endpoint). No match → positive response.
- Config is **in-memory only** (ephemeral); restart re-seeds defaults. Accepted trade-off.
- UI served by FastAPI itself at `/admin`; CRUD API under `/admin/rules`, guarded by a shared-secret env var.
- **Render**: fully covered on the current free plan, single web service, `render.yaml` unchanged. Caveats: free instances spin down after idle (config wiped — accepted); single instance so no state-sync concern. `ADMIN_KEY` set in the Render dashboard, not committed.

## 2. Assumptions

1. One rule = one endpoint's behavior for that airline+route (endpoint is part of the exact-match key).
2. Absence of a rule means positive; rules only define negatives.
3. Latency/timeout injection is **out of scope** for v1.
4. No audit trail of rule changes.
5. Existing pytest/Newman suites keep passing with seed rules in place.

## 3. Decision Log

| # | Decision | Alternatives considered | Rationale |
|---|----------|------------------------|-----------|
| 1 | Scope = all capabilities | BPI only; BPI + pre-issuance | Testers need failure control across the whole booking chain. |
| 2 | Preset failures + custom code/msg override | Presets only; fully custom JSON; +delay injection | Flexibility without risking schema-invalid responses. |
| 3 | Ephemeral in-memory config | Persistent disk (paid); external store; env-seeded | Matches existing state model (orders are in-memory too); keeps Render free plan. |
| 4 | UI served by FastAPI (static HTML + vanilla JS) | Separate React static site; API-only | One deploy, no CORS, no build step; matches team size. |
| 5 | Exact-match rules, positive default — with ONE scoped wildcard: the `airline` field may be the literal `"*"` (any airline). Origin/destination/endpoint stay exact-match. Lookup precedence: exact airline before `"*"`, exact flow before null | Fully exact match (no wildcards); generic wildcards with specificity; per-endpoint toggle lists | Simplest predictable matching; the airline wildcard is required so seeds preserve the carrier-agnostic behavior of the deleted `is_route_blocked`. |
| 6 | Shared-secret auth (`X-Admin-Key` ↔ `ADMIN_KEY` env) | No auth; reuse mock token flow | Public Render URL; ~20 LOC; admin disabled entirely if env unset. |
| 7 | Rule-registry service + per-handler guard (Approach A) | Jinja server-rendered admin (B); middleware interceptor (C) | Matches codebase style (in-memory singletons, thin routers); middleware would duplicate per-endpoint parsing incl. TSY decryption. |
| 8 | orderDetail is **flow-aware**: optional `flow` field (`submitBooking` = pre-pay / `issuance` = post-pay / null = both), inferred server-side from stored order status | Caller-supplied flow hint | Mock already knows order status; no contract change for callers. |
| 9 | Positive path keeps **immediate `pay → ISSUED`** | Nth-poll ISSUING→ISSUED baseline; time-based | Zero existing-test churn; ISSUING appears only when a rule injects it. |
| 10 | No `issuing_then_issued` preset; no poll-state tracking | Per-order poll counter for N-polls-then-ISSUED | User confirmed not needed — positive case is immediately ISSUED; ISSUING only exists via `stuck_issuing`. |
| 11 | **TSY BPI endpoints: presets only — no code/msg override.** `PUT /admin/rules` rejects (422) overrides on `tsy.*`; UI disables the fields | Allow overrides everywhere with per-contract type coercion | TSY failures are fixed shapes (HTTP 500, string `status` envelope); overrides added typing complexity for no test value. |
| 12 | **Wildcard-airline amendment (user-approved, 2026-07-19):** seeds are **6 rules** with airline `"*"` — SIN→KUL and SIN→CGK blocked for ANY airline on `tsy.order`, `std.baggageSearch` and `std.order`. Wildcard is allowed ONLY on the airline field | 4 exact-airline seeds per the original draft | The deleted `is_route_blocked` was carrier-agnostic; exact-airline seeds would have silently changed behavior for non-seeded carriers (e.g. TR). |

## 4. Rule model

```python
Rule = {
  "endpoint": str,      # ENDPOINTS key, see §5
  "airline": str,       # e.g. "JT", or "*" = any airline (the only wildcard, Decision 12)
  "origin": str,        # e.g. "CGK"
  "destination": str,   # e.g. "SIN"
  "flow": str | None,   # orderDetail endpoints only: "submitBooking" | "issuance" | None (both)
  "preset": str,        # key into PRESETS[endpoint]
  "code": str | None,   # optional override — NOT allowed for tsy.* endpoints (422)
  "msg": str | None,    # optional override — NOT allowed for tsy.* endpoints (422)
}
```

Override validation: for endpoints that allow overrides, `code` is validated/coerced to the
contract's type (int for core ticketing and std envelopes) at PUT time; invalid values are
rejected with 422 so responses stay schema-valid. `GET /admin/presets` exposes an
`overridable` flag per endpoint so the UI disables the fields for `tsy.*`.

`RuleStore` (`app/services/scenario_rules.py`, same singleton pattern as `orders.py`):
`dict[(endpoint, airline, origin, destination, flow) → Rule]`. One rule max per key; PUT replaces.
`check(endpoint, airline, org, dst, flow=None)` → `Rule | None`; lookup order is
`(airline, "*") × (flow, None)` — exact airline beats the wildcard, exact flow beats null.

Validation: shape only (airline `^[A-Z0-9]{2}$` **or** the literal `"*"`; airports
`^[A-Z]{3}$`). Unknown airline/airport is accepted and simply never matches — keeps UI
usable for future airlines.

**Seed rules** (loaded at startup and on reset): **6 rules with wildcard airline `"*"`** —
the 2 blocked routes (SIN→KUL, SIN→CGK) × 3 endpoints (`tsy.order`, `std.baggageSearch`,
`std.order`), reproducing the carrier-agnostic `BLOCKED_SECOND_BAGGAGE_ROUTES` exactly
(Decision 12). TSY search is NOT seeded — it succeeds on blocked routes today (blocking is
order-time only). That constant and both `is_route_blocked` helpers are deleted; behavior
preserved so existing BPI tests pass unchanged.

## 5. Endpoints & preset catalog

12 configurable endpoint IDs (auth/token excluded — no airline/route context):

| Group | Endpoint IDs |
|-------|--------------|
| Ticketing | `search`, `preOrderVerify`, `ancillarySearch`, `order`, `pay`, `orderDetail` |
| TSY BPI | `tsy.secondBaggage`, `tsy.order`, `tsy.orderDetail` |
| Standardized BPI | `std.baggageSearch`, `std.order`, `std.orderDetail` |

Static catalog `PRESETS[endpoint] = {preset_key: {label, default_code, default_msg, kind}}`.
`kind` drives rendering: `empty_result`, `business_error`, `http_500`, `status_override`.
Examples: `search → no_results` (airline filtered out of results — a supplier with no inventory
is not an error); `order → order_failed (500)`; `pay → payment_declined`; `std.* → 555 / 5001 / 400`;
`tsy.* → http_500` (encrypted iff request was encrypted, per BPI_DESIGN §1.12).

Flow-specific presets for the three orderDetail endpoints:

- `submitBooking` flow: `order_not_found`, `unpaid_missing_data`
- `issuance` flow: `stuck_issuing` (always ISSUING, never advances — negative case, stateless),
  `issue_failed` (terminal failure status/code)

UI dropdowns are driven entirely by `GET /admin/presets`; no hardcoded lists in JS.

## 6. Endpoint integration

One guard per handler, after request validation, before the happy path:

```python
rule = rules.check("order", airline, ori, dest)
if rule:
    return scenario_responses.render(rule)
```

Airline/route sources per endpoint:

- `search` / `ancillarySearch`: request body directly
- `preOrderVerify` / `order`: decoded offerKey
- `pay` / `orderDetail`: stored order's offer (request only carries orderId; rules still keyed on airline+route)
- `orderDetail` flow: stored status `UNPAID` → `submitBooking`, else `issuance`
- TSY BPI: segment `depAirport`/`arrAirport`; decryption handling unchanged; failure re-encrypted if request was encrypted
- Standardized BPI: `departureAirport`/`arrivalAirport`; failures via existing `{code,msg,data}` helpers

`scenario_responses.render(rule)`: dispatch on preset `kind`, apply code/msg overrides, reuse each
contract's existing envelope helpers so failure shapes are byte-identical to today's hard-coded ones.

## 7. Admin API & UI

Router `app/routers/admin.py`; every endpoint behind an `X-Admin-Key` dependency checked against
env `ADMIN_KEY` (401 on mismatch; **admin disabled entirely if `ADMIN_KEY` unset**).

- `GET /admin/rules` — list (each with deterministic `rule_id` = hash of key tuple)
- `PUT /admin/rules` — upsert (silent replace on same key; "editing = re-adding")
- `DELETE /admin/rules/{rule_id}`
- `POST /admin/rules/reset` — wipe + reload seeds
- `GET /admin/presets` — endpoints, presets, flow-capable endpoints, airline codes from `config.AIRLINES`

UI: single static `app/static/admin.html` served at `GET /admin` (page itself unauthenticated;
prompts once for the key, holds it in a JS variable, sends it as header on every fetch).
Layout (validated via lo-fi mockup): header (title + admin-key status/change) · "Add rule" panel
with two rows — match key (endpoint ▾, preset ▾, airline ▾, origin, destination, flow ▾) and
overrides (code, msg, Add button) · "Active rules" table (endpoint, airline, route, flow, preset
+ seed badge, code/msg, per-row delete) with a Reset-to-defaults action and a footer note about
replace-on-same-key and reset-on-restart. Behavior: preset ▾ repopulates per endpoint; flow ▾
enabled only for orderDetail endpoints; code/msg disabled for `tsy.*`; airline ▾ shows airline
identifiers only (no flight numbers), read live from `config.AIRLINES`, plus an
"Any airline (*)" wildcard option and a free-text escape hatch for non-catalog carriers
(e.g. TR). Seed rules are deletable like any other. Vanilla JS + fetch; no build step; no new
Python dependencies.

## 8. Edge cases

- Rule added after order creation: applies immediately (checks run per-request against stored order). Deletion likewise immediate.
- All presets are stateless — no per-order counters needed (see Decision 10).
- TSY encrypted request + rule: render failure, then encrypt (symmetry preserved).
- Restart: re-seed blocked-route rules; everything else gone (accepted).

## 9. Testing — TC-SCN test matrix

Implemented in `tests/test_scenario_rules.py` (groups A–B) and
`tests/test_scenario_injection.py` (groups C–D). Conventions follow TEST_CASES.md
(canonical fixture GA, KNO→CGK, 2026-09-20 where applicable).

### A. Rule admin (feature in isolation)

| ID | Case | Priority |
|----|------|----------|
| SCN-01 | CRUD lifecycle: PUT → GET shows it → DELETE → GET empty | P0 |
| SCN-02 | Auth: no key → 401; wrong key → 401; `ADMIN_KEY` unset → admin disabled | P0 |
| SCN-03 | PUT same key twice → silent replace, still one rule | P1 |
| SCN-04 | Reset → only the 6 wildcard-airline seed rules remain | P1 |
| SCN-05 | Validation: bad airport shape → 422; unknown-but-valid-shape airline accepted (never matches, no crash); non-int `code` override on core/std endpoints → 422; **any code/msg override on `tsy.*` → 422** (Decision 11) | P0 |
| SCN-06 | `GET /admin/presets`: all 12 endpoints, flow-capable + `overridable` flags, all airlines from `config.AIRLINES` | P2 |

### B. Exact-match semantics (near-miss suite)

| ID | Case | Priority |
|----|------|----------|
| SCN-10 | Rule GA KNO→CGK on `order`: GA KNO→CGK fails; GA CGK→KNO succeeds (direction matters) | P0 |
| SCN-11 | Same rule: JT KNO→CGK succeeds (airline isolation) | P0 |
| SCN-12 | Same rule: GA KNO→CGK `pay` succeeds (endpoint isolation) | P0 |
| SCN-13 | Flow targeting: `orderDetail`+`issuance` rule → pre-pay orderDetail succeeds, post-pay fails; inverse for `submitBooking` | P0 |
| SCN-14 | Flow=null rule hits both pre- and post-pay orderDetail | P1 |

### C. Cross-feature interaction

| ID | Case | Priority |
|----|------|----------|
| SCN-20 | Search-rule containment: capture offerKey via clean search → add `search` no_results rule for GA → preOrderVerify/order with old offerKey still succeed. Also: search with `airlineIds:["GA"]` only → `data.offers == []` inside a **success** envelope (`code == 0`), not an error | P0 |
| SCN-21 | `pay`/`orderDetail` rules match via the stored order's airline/route (request carries only orderId) | P0 |
| SCN-22 | Rule added mid-flow (after order, before pay) takes effect; deleted mid-flow stops applying | P1 |
| SCN-23 | Pre-issuance: `ancillarySearch` no_results → empty ancillary list (schema-valid success); subsequent order without ancillaries still works | P1 |
| SCN-24 | TSY BPI §1.12 symmetry: encrypted request + rule → **encrypted** preset failure (decrypt, assert shape); plaintext request → plaintext failure. Preset-only shape (no overrides) | P0 |
| SCN-25 | Standardized BPI rule failure → HTTP 200 `{code:555,...}` envelope, never HTTP 5xx | P0 |
| SCN-26 | Same airline+route negative in TSY but not Standardized → contracts independent | P1 |
| SCN-27 | `stuck_issuing` on std vs core orderDetail: ISSUING in each contract's own status vocabulary | P1 |
| SCN-28 | `order_not_found` preset fires with a **valid** orderId (rule-injected), distinguished from the genuine bogus-orderId path — same shape, different trigger | P1 |

### D. Regression (release gate)

| ID | Case | Priority |
|----|------|----------|
| SCN-30 | Full existing pytest suite green with seed rules loaded (seeds behavior-identical to deleted `BLOCKED_SECOND_BAGGAGE_ROUTES`) | P0 |
| SCN-31 | Newman collection (22 requests, 61 assertions) green, no collection changes | P0 |
| SCN-32 | Delete a seed rule → SIN→KUL second baggage succeeds (blocking is truly rule-driven) | P0 |
| SCN-33 | TC-E2E-01 golden path green with an unrelated rule present (no bystander effect) | P1 |

Postman "scenario config" folder: deferred, out of scope for v1.

## 10. Out of scope (v1)

Latency/timeout injection · wildcard matching beyond the airline field (Decision 12) ·
persistence across restarts · audit trail ·
fully custom JSON responses · separate frontend app · concurrent rule mutation by multiple
testers mid-run (last-write-wins, no locking — known limitation).
