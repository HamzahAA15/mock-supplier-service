# Standardized BPI (Baggage Post Issuance) — Design

Status: **Implemented**
Version label: **Standardized BPI** (sibling of the existing tsy-bpi version; more versions may follow)
Contract source of truth: PRD "Standardized 3PS Baggage Post Issuance Automation", section V (Standardized Ancillary Post-Issuance API Specification) + its API JSON Samples.
Related: `BPI_DESIGN.md` (tsy-bpi, implemented), `bpi-rq-rs/standardizedv3-bpi/` (older samples — superseded where they conflict with the PRD).

---

## 1. Understanding Summary

- A second, parallel BPI implementation in the mock supplier service: the Standardized Ancillary Post-Issuance contract, alongside the existing tsy-bpi flow — same second-baggage behavior, different contract.
- Endpoints: `POST /ancillary/v1/baggage/search`, `POST /ancillary/v1/orders`, `GET /ancillary/v1/orders/{ancillaryOrderNo}`. Envelope: `{"code": int, "msg": str, "data": obj|null}`, always HTTP 200.
- Auth: `Authorization` header accepted but never validated; requests are never rejected for auth reasons.
- Search reuses the 9 tsy baggage tiers (20–100 kg, same USD prices) as `CHECKEDBAGGAGE` offers; with passengers → `passengerOffers` per pax, without passengers (pre-issuance live fetch) → `generalOffers`.
- `ancillaryKey` is a self-describing base64-encoded segment context + weight; order decodes it to validate and reconstruct segments — stateless, restart-tolerant.
- Order stores in memory keyed by client-supplied `ancillaryOrderNo`; order RS returns `ISSUING`; orderDetail always returns `ISSUED`. No pay step.
- Error cases (all HTTP 200 envelope): blocked routes SIN→KUL / SIN→CGK → code 555; unknown `ancillaryOrderNo` or invalid `ancillaryKey` → code 400; past `departureTime` → code 5001.
- Existing tsy-bpi endpoints remain untouched.

## 2. Assumptions

1. PRD §V + JSON samples are authoritative; `bpi-rq-rs/standardizedv3-bpi/` samples are superseded where they conflict.
2. Obvious PRD sample typos (missing commas, `departureDate` vs `departureTime`, stray annotation text) are normalized to the field tables.
3. Baggage semantics = ADDITIONAL (per PRD meeting notes); for the mock this means full tiers are returned regardless of any `existingAncillary` info.
4. Not simulated (YAGNI, deselected during brainstorming): `PARTIALLY_ISSUED` / `CANCELLED` statuses, price-drift / `postpaidBaggageIssueThreshold` scenarios, multi-PNR special handling beyond echoing passengers, time- or poll-based status transitions.
5. Mock style follows repo conventions: permissive Pydantic models (`PermissiveModel`), router-side validation (no FastAPI 422), verbatim echo of request fields where the contract requires.
6. In-memory order store (lost on restart) is acceptable, same as tsy-bpi.

## 3. Decision Log

| # | Decision | Alternatives considered | Rationale |
|---|----------|------------------------|-----------|
| 1 | Label this version **Standardized BPI**, module prefix `standardized_bpi` | `std_bpi`, overloading existing `bpi` modules | Future BPI versions expected; explicit label keeps versions distinguishable |
| 2 | **Approach A**: parallel module set, shared catalog constants imported from `bpi_catalog.py` | B: extract shared `bpi_core` + adapters; C: single router with version dispatch | Zero risk to working tsy flow; contracts differ enough that a shared core would be thin; version flag belongs to Traveloka's side, not the mock |
| 3 | Auth: accept `Authorization` but don't validate | Enforce Bearer (403); no auth | Lowest client-testing friction while keeping the header in the contract |
| 4 | Lifecycle: order RS `ISSUING`, orderDetail always `ISSUED` | Time-based transition; poll-count based | Matches PRD JSON sample literally; simplest, fully deterministic |
| 5 | Catalog: reuse the 9 tsy tiers (20–100 kg) | PRD sample tiers only (20/25 kg); tiers + price-drift route | "Same behaviour" as existing BPI; single shared catalog |
| 6 | Errors: 555 blocked route, 400 unknown order / invalid key, 5001 past departure | 403 auth, PARTIALLY_ISSUED magic pax, HTTP 500 like tsy | Selected set covers the contract's result codes relevant to the mocked behavior; standardized contract uses envelope codes, not HTTP errors |
| 7 | `ancillaryKey`: self-describing base64-encoded segment context + weight | Deterministic hash (tsy style); literal readable keys | Order RQ carries no segments, so the key must be reversible for order to validate and reconstruct segments statelessly (offer_key.py philosophy) |
| 8 | Key wire format: base64url of a compact JSON envelope | Pipe-delimited string (original sketch) | Same reversibility, but robust for multi-segment routes and field values containing delimiters |

## 4. Architecture (Approach A)

```
app/models/standardized_bpi.py           # request models (PermissiveModel subclasses)
app/services/standardized_bpi_catalog.py # key encode/decode, offer building, validation
app/services/standardized_bpi_orders.py  # StandardizedBpiOrderStore (in-memory singleton)
app/routers/standardized_bpi.py          # APIRouter(prefix="/ancillary/v1")
tests/standardized_bpi_helpers.py
tests/test_standardized_bpi_search.py
tests/test_standardized_bpi_order.py
tests/test_standardized_bpi_order_detail.py
tests/test_standardized_bpi_e2e.py
```

Shared imports from `app/services/bpi_catalog.py`: `BAGGAGE_TIERS`, `TIER_WEIGHTS`, `CURRENCY`, `BLOCKED_SECOND_BAGGAGE_ROUTES`. No changes to existing tsy modules; `app/main.py` registers `standardized_bpi.router`. The conftest `_reset_store` fixture also clears the standardized store.

Envelope helpers (in the router):

```python
def ok(data):       return {"code": 0,    "msg": "Success", "data": data}
def err(code, msg): return {"code": code, "msg": msg,       "data": None}
```

Result codes used: `0` success, `400` invalid order no / ancillary key / passenger, `555` no ancillary quotation (blocked route, unsupported ancillaryType, empty routes), `5001` prohibition of sale (past departure). Codes `3`, `403`, `500` are defined by the contract but not actively produced by the mock.

## 5. ancillaryKey Encoding

```
payload = ["SBPI", tripType, weight, [[marketingCarrier, flightNumber, operatingCarrier,
           operatingFlightNumber, departureAirport, arrivalAirport, departureTime,
           arrivalTime], ...one tuple per segment]]
key     = base64url(compact JSON of payload)   # one key per (route segment-chain, tier)
```

- All eight segment fields needed for the standardized Segments Element are encoded, so the order RS reconstructs every segment exactly; `operatingCarrier`/`operatingFlightNumber` default to the marketing values when absent in the search RQ.
- Keys are identical across passengers for the same (route, tier), matching the PRD sample.
- Decode failure, wrong prefix, malformed structure, or weight not in `BAGGAGE_TIERS` → order fails with code 400 `"invalid ancillaryKey"`.
- Property: `decode(encode(x)) == x`; stateless between search and order; restart-tolerant.

## 6. Endpoint Behavior

### 6.1 `POST /ancillary/v1/baggage/search`

`StandardizedBpiSearchRequest`: `ancillaryType`, `routes[]` (raw dicts), `passengers[]` (raw dicts, optional), `ticketingFunnel` (optional, ignored).

1. `ancillaryType != "CHECKEDBAGGAGE"` → 555.
2. Empty/missing `routes` → 555.
3. Any segment on a blocked route → 555 (whole request).
4. Any segment with parseable past `departureTime` → 5001 (unparseable/missing tolerated).
5. Else `data`: `currency: "USD"`, `routes[]` echoing `tripType` + RQ segments verbatim, and:
   - passengers present → `passengerOffers[]`, one per RQ passenger (`passengerId` echoed), each with the 9-tier `ancillaryOffers[]`;
   - passengers absent → `generalOffers[]` with one entry holding the 9-tier `ancillaryOffers[]`.

Each offer: `{ancillaryKey, ancillaryType: "CHECKEDBAGGAGE", ancillaryCode: <kg>, ancillaryPiece: 1, unitOfMeasurement: "WEIGHT", price}`.

### 6.2 `POST /ancillary/v1/orders`

`StandardizedBpiOrderRequest`: `ancillaryOrderNo`, `isCross`, `passengers[]`, `selectedAncillary[]`, `ticketingFunnel` (optional).

1. Missing `ancillaryOrderNo` → 400 `"invalid ancillary order number"`.
2. Empty `selectedAncillary` → 400.
3. Per item: `passengerId` must exist in `passengers[]` (else 400); `ancillaryKey` must decode (else 400 `"invalid ancillaryKey"`); decoded segments on a blocked route → 555.
4. `total = Σ tier prices`; `createdTime`/`updatedTime` = now (`yyyy-MM-dd HH:mm:ss`); `isCross` echoed (default `true`).
5. `store.upsert(ancillaryOrderNo, record)` — idempotent, latest wins. Failures return before the store is touched (failed orders are never created).
6. RS `data`: `{ancillaryOrderNo, orderStatus: "ISSUING", total, currency, isCross, createdTime, updatedTime, passengers (echo), selectedAncillary[]}`; each selected item: `{passengerId, ancillaryKey, ancillaryType, ancillaryCode, ancillaryPiece, price, segments[] (reconstructed from key)}`.

### 6.3 `GET /ancillary/v1/orders/{ancillaryOrderNo}`

1. Unknown order → 400 `"invalid ancillary order number"` (`data: null`).
2. Else stored record with `orderStatus: "ISSUED"` (always, repeatable across polls), `updatedTime` = now, and each `selectedAncillary` item additionally carrying `unitOfMeasurement: "WEIGHT"`.

## 7. Edge Cases

- Key with unknown/forged weight tier → 400 (decode validates against `BAGGAGE_TIERS`).
- Re-posting the same `ancillaryOrderNo` → upsert, latest wins (idempotent retry semantics).
- Search with empty `routes` → 555.
- Duplicate `selectedAncillary` entries → allowed, both priced.
- Server restart between order and orderDetail → order lost → 400 (documented mock limitation, same as tsy).
- Passengers without `passengerId` → offers still emitted, `passengerId` echoed as given (PRD: nullable when passengers absent).
- Keys from a pre-issuance (generalOffers) search remain orderable later — supports the post-to-pre fetching flow.

## 8. Testing

Implemented in `tests/test_standardized_bpi_*.py` (see `TEST_CASES.md` § "Standardized BPI" for the full case table): key round-trip incl. multi-segment and forged keys, passengerOffers vs generalOffers, 555/5001/400 negatives, idempotent upsert, ISSUED repeatability, segment reconstruction, tsy/standardized coexistence. Postman folder "Standardized BPI" (`SBPI-1…7`) chains the key and order number via collection variables.

## 9. Out of Scope

Token validation / 403 flows, `PARTIALLY_ISSUED`/`CANCELLED` simulation, price-drift & issuance threshold checks, seat ancillaries, `existingAncillary`-aware offer filtering, persistence across restarts, changes to tsy-bpi endpoints.
