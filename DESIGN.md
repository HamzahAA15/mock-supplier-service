# Mock Supplier Service — Design

Status: **Design (pre-implementation)** · Owner: Hamzah Alfauzi · Date: 2026-07-04

A FastAPI service that mimics a Traveloka flight **supplier** (partner API server).
It returns deterministic, schema-shaped mock inventory across the core booking chain
so the Traveloka aggregator can be integration-tested without a real airline backend.

Contract source: `Traveloka-api-guideline/[Published]-Traveloka-API-Document-Integration-v3.md`
and the `API sample/` request/response captures.

---

## 1. Understanding summary

- **What:** Mock supplier covering the core happy path
  `token → search → preOrderVerify → ancillarySearch → order → pay → orderDetail`,
  on the exact contract paths.
- **Why:** A deterministic, restart-tolerant stub for aggregator integration/QA.
- **Who:** Integration + QA engineers.
- **Airlines (v1):** `JT`, `GA`, `QZ` — one flight each, returned for *any* route and *any* future date.
- **Product:** `BASIC` only; no modified inventory.
- **Non-goals (v1):** auth enforcement, `cancel`, `getseat`, round-trip, transit/stopover,
  non-BASIC products, cross-restart persistence, rate limiting.

---

## 2. Assumptions (confirmed)

1. **Language:** FastAPI (Python). Traveloka is not a Go shop; onboarding Go is high-friction.
2. **offerKey:** deterministic, stateless base64 encoding — see §6.
3. **Currency:** `USD`.
4. **Order store:** in-memory dict keyed by `orderId`. Lost on restart (acceptable).
5. **Auth:** `/uaa/oauth/token` returns a dummy bearer token; no endpoint enforces it in v1.
6. **Success envelope:** `code: 0, msg: "success"` (confirmed from samples — NOT HTTP 200 as the body code).
7. **TDD:** pytest + FastAPI `TestClient`, red-green per endpoint.

---

## 3. Requirements traceability

| # | Requirement | Where handled |
|---|---|---|
| 1 | All routes return this inventory | Search ignores `oriAirport`/`destAirport` for offer generation; echoes them into segments (§7.2) |
| 2 | All dates onward return this inventory | Flight times computed relative to requested `depDate` (§7.2) |
| 3 | Cannot retrieve backdate inventory | `depDate < today` → result code **205** (§7.2) |
| 4 | All product BASIC, no modified inventory | `product: ["BASIC"]` hard-coded everywhere |
| 5 | Same offerKey from search → orderDetail | Deterministic stateless offerKey (§6); order store also retains it |
| 6 | Randomize 10-digit orderId | `random 10-digit numeric string` at order time (§7.5) |
| 7 | Echo passenger details from request | Order stores and OrderDetail returns request passengers verbatim (§7.5, §7.7) |
| 8 | JT & QZ FBA 0 kg, GA 20 kg | Per-airline `FREECHECKEDBAGGAGE` in Search + AncillarySearch (§4, §7.2) |
| 9 | Ancillary options = multiples of 5 above FBA | AncillarySearch generates 3 `CHECKEDBAGGAGE` options (§7.4) |

### 3.1 Echo principle (must hold)

**The service never invents route, date, or passenger data — it echoes what the request supplied.**
The airlines (JT/GA/QZ), flight numbers, times-of-day, aircraft, fares and FBA are the only fixed
mock inventory; the *route*, *departure date*, and *passenger/contact details* are always taken from
the incoming request and reflected back in the response.

- **Search — echo route + date into every offer's segments.**
  Request `KNO → CGK`, `depDate 2026-09-20` ⇒ response returns three offers (JT, GA, QZ), and each
  offer's `segments` has `depAirport: "KNO"`, `arrAirport: "CGK"`, and `depTime`/`arrTime` anchored to
  `2026-09-20` (e.g. JT `2026-09-20 08:00:00 → 2026-09-20 10:00:00`). The same `oriAirport`/`destAirport`
  and `depDate` are also encoded into each `offerKey`, so they survive to every downstream call.

- **Order — echo the whole order request.** The Order response (and later OrderDetail) reflects back the
  exact `passengers` and `contacts` submitted, the `segments` (route/date) resolved from the `offerKey`,
  and the `addedAncillary` resolved from the submitted `ancillaryKeyLists`. If the request carries
  **3 passengers**, the response carries **3 passengers** — same names, types, birthdays, IDs, in order.
  Contacts are echoed the same way.

This principle is what makes requirements #1, #2, and #7 concrete, and is asserted directly in the
Search and e2e tests (§9).

---

## 4. Mock inventory (per airline)

Single flight per airline, applied to *whatever* route/date is searched. Times are local,
anchored to the requested `depDate`.

| Airline | Flight | Dep → Arr | Duration | Aircraft | FBA (kg) | BASIC fare (USD) | Tax (USD) |
|---|---|---|---|---|---|---|---|
| JT | JT100 | 08:00 → 10:00 | 120 min | B739 | **0**  | 60.00 | 8.00 |
| GA | GA200 | 12:00 → 14:00 | 120 min | B738 | **20** | 95.00 | 12.00 |
| QZ | QZ300 | 16:00 → 18:00 | 120 min | A320 | **0**  | 55.00 | 7.00 |

- `marketingCarrier` = `operatingCarrier` = airline code; `codeShare: false`.
- `seatCount`: fixed (e.g. 9); `cabin: "Y"`, `seatClass: "Y"`.
- Fares are per adult. Child = 75%, infant = 10% (mock rule) — applied in `charges`.
- If `airlineIds` is supplied in the request, filter offers to that subset; otherwise return all three.

---

## 5. Architecture

```
mock-supplier-service/
├── app/
│   ├── main.py              # FastAPI app, router registration
│   ├── config.py            # constants: airlines, fares, currency, FBA
│   ├── models/              # Pydantic request/response models per endpoint
│   │   ├── common.py        # Envelope(code,msg,data), Segment, Offer, Ancillary...
│   │   ├── search.py
│   │   ├── verify.py
│   │   ├── ancillary.py
│   │   ├── order.py
│   │   ├── pay.py
│   │   └── order_detail.py
│   ├── services/
│   │   ├── inventory.py     # builds offers/flights/segments from config + request
│   │   ├── offer_key.py     # encode/decode deterministic offerKey
│   │   ├── ancillary.py     # baggage option generation (multiples of 5)
│   │   ├── orders.py        # in-memory OrderStore, orderId/PNR/ticket generation
│   │   └── codes.py         # result-code constants + envelope helpers
│   └── routers/
│       ├── auth.py          # POST /uaa/oauth/token
│       └── flight.py        # POST /flight/{search,preOrderVerify,ancillary/search,order,pay,orderDetail}/v3
├── tests/                   # pytest, one module per endpoint + e2e chain
├── requirements.txt
└── README.md
```

- **Framework:** FastAPI + Uvicorn. **Validation/serialization:** Pydantic v2.
- **Response envelope:** every endpoint returns `{ "code": int, "msg": str, "data": {...} }`,
  HTTP 200 with the business result in `code` (`0` = success).
- **Field casing:** camelCase in JSON via Pydantic aliases; snake_case internally.
- **Statelessness:** search/verify/ancillary are pure functions of the request (via offerKey).
  Only order/pay/orderDetail touch the in-memory store.

---

## 6. offerKey scheme

Deterministic, reversible, opaque-looking. Encodes everything needed to rebuild an offer,
so downstream calls need no shared search state (satisfies req #5 trivially).

```
raw     = "JT|CGK|DPS|2026-07-10|BASIC"
offerKey = base64url(raw)          # e.g. "SlR8Q0dLfERQU3wyMDI2LTA3LTEwfEJBU0lD"
```

- Search generates one offerKey per offer (per airline).
- `preOrderVerify`, `ancillarySearch`, `order` all `decode(offerKey)` to reconstruct the flight.
- Malformed/undecodable offerKey → result code **101** (verify) / route-specific error.
- `ancillaryKey` format mirrors the samples: `"{adt}_{chd}_{inf}${flightNumber}$PA{kg}"`
  e.g. `1_0_0$GA200$PA25`. Also reversible for the Order call.

---

## 7. Endpoint specifications

All paths are `POST`. Success = `code: 0, msg: "success"` unless noted.

> **Concrete request/response JSON for every endpoint is in [`API_SCHEMAS.md`](./API_SCHEMAS.md).**
> The sections below describe behavior and validation; the schemas file gives exact wire shapes.

### 7.1 `POST /uaa/oauth/token`
- **Req:** `{ "grantType": "clientCredentials" }` (+ Basic auth header, ignored).
- **Res:** `{ "accessToken": "<uuid>", "tokenType": "Bearer", "expiresIn": 3600, "scope": "search preOrderVerify ancillarySearch order pay orderDetail" }`.
- No `code` envelope (matches the auth sample).

### 7.2 `POST /flight/search/v3`
- **Req (key fields):** `product?`, `routes[]` (`oriAirport`, `destAirport`, `depDate`, `cabin[]`),
  `adultNumber`, `childNumber`, `infantNumber`, `airlineIds?`, `nonstop?`.
- **Validation → result codes:** missing route → 206; missing airports → 201; missing depDate → 203;
  bad date format → 204; **`depDate` earlier than today → 205**; no adult → 241.
- **Success `data`:** `offers[]`, `penalties[]`, `ancillaries[]`, `flights[]`, `segments[]`, `currency: "USD"`.
  - One offer per eligible airline. `routeIndex: 0` (one-way only in v1).
  - `offers[].offerKey` per §6; `product: ["BASIC"]`; `charges[]` = FARE+TAX per pax type.
  - `ancillaries[]` includes each airline's `FREECHECKEDBAGGAGE` (`ancillaryCode` = FBA kg,
    `ancillaryPiece: 1`, or `0` when FBA is 0 kg — confirmed 2026-07-05, matching API_SCHEMAS.md;
    `unitOfMeasurement: "WEIGHT"`); `freeAncillaryRefs` link offer→ancillary.
  - **Echo (req #1, #2):** `segments[]` are built from the requested `oriAirport`/`destAirport` and
    `depDate` — the response route/date always equals the request route/date; only flight number, time-of-day,
    aircraft, fare and FBA are the fixed per-airline mock values. One segment per airline, echoing the same route.

### 7.3 `POST /flight/preOrderVerify/v3`
- **Req:** `{ "offerKey": "..." }`.
- **Validation:** empty offerKey → 101; undecodable → 204.
- **Success:** re-returns the same Search-shaped `data` for that single offer (no price change → `code: 0`).

### 7.4 `POST /flight/ancillary/search/v3`
- **Req:** `{ "offerKey": "..." }`.
- **Success `data`:** `{ "currency": "USD", "ancillaryOffers": [...] }`.
- Generates **3 `CHECKEDBAGGAGE`** options as multiples of 5 above the airline's FBA:
  - JT/QZ (FBA 0): 5, 10, 15 kg → e.g. price `kg * 1.5` USD.
  - GA (FBA 20): 25, 30, 35 kg.
  - Each: `ancillaryKey` (§6), `ancillaryCode` (kg), `ancillaryPiece: 1`, `unitOfMeasurement: "WEIGHT"`,
    `desc: "<kg>kg"`, `oriAirport`, `destAirport`, `transferAirport: ""`, `flightNumber`, `price`.

### 7.5 `POST /flight/order/v3`
- **Req:** `offerKey`, `passengers[]`, `contacts[]`, `ancillaryKeyLists?[]` (`passengerIndex`, `ancillaryKeys[]`).
- **Validation:** empty contact email → 529; bad email → 530; empty phone → 531; expired ancillary → 553.
- **Behavior:**
  - Generate **10-digit numeric `orderId`** (req #6) and a **6-char alphanumeric PNR**.
  - Resolve each `ancillaryKey` → `addedAncillary[]` (grouped by passenger).
  - `total` = fares + taxes (**× passenger count, per type**) + selected ancillary prices.
  - **Echo (req #7):** store and reflect back the request verbatim — all `passengers` (N in → N out,
    same order and fields) and all `contacts`. `segments` (route/date) are reconstructed from the `offerKey`,
    so they match the original search. Nothing about the passengers is synthesized.
  - Store order: `{orderId, pnr, offerKey, passengers, contacts, addedAncillary, total, status: "UNPAID",
    createdTime, expiredTime (=+30 min), ticketNumbers: {}}`.
- **Success `data`:** `currency`, `total`, `orderId`, `expireInMinutes: 30`, `addedAncillary[]`,
  `product: ["BASIC"]`, `issuanceTimeInMins: 120`, `offers[]`, `penalties[]`, `ancillaries[]`,
  `flights[]`, `segments[]`.

### 7.6 `POST /flight/pay/v3`
- **Req:** `orderId`, `payType?` (default `BPA`), `accountNumber?`.
- **Validation:** empty orderId → 745; order not found → 148; already paid → 748.
- **Behavior:** set status `ISSUED`, `payTime = now`, generate a **13-digit ticketNumber per passenger**.
  Order `expiredTime` is informational only — expiry is **not enforced** at pay (confirmed 2026-07-05).
- **Success `data`:** `{ "transactionId": "<id>", "amount": "<total>", "currency": "USD", "accountNumber": "" }`.

### 7.7 `POST /flight/orderDetail/v3`
- **Req:** `{ "orderId": "..." }`.
- **Validation:** empty orderId → 745; not found → 148.
- **Success `data`:** `orderInfo` (`orderId`, `product: ["BASIC"]`, `issuanceTimeInMins`, `status`,
  `createdTime`, `updateTime`, `expiredTime`, `payTime`, `amount`, `currency`, `accountNumber`),
  `pnrs[]` (`pnr`, `providerPnr`, `email`, `segments[]` (light), `passengers[]` with `passenger` `"LAST/FIRST"`,
  `ticketNumber` (populated once ISSUED), `cardNumber` (echoed from the pax)), `ancillaryList[]`,
  `penalties[]`, `ancillaries[]`, `flightRefs[]` (`flightIndex`, `fareType`, `brandedFare`), `flights[]`,
  `passengerList[]` (echoed verbatim, req #7), `contactList[]`, `segments[]` (**full** segment objects).
  - **Segment shape note:** the top-level `segments[]` are full objects (as in Search); the nested
    `pnrs[].segments[]` and `ancillaryList[].segments[]` are light (`depAirport`/`arrAirport`/`flightNumber`).
    Matches the live supplier `orderDetail`/`submitBooking` capture.

---

## 8. Result codes used

| Code | Meaning | Endpoints |
|---|---|---|
| 0 | success (also "price changed but data valid") | all |
| 101 | offerKey cannot be empty | verify |
| 148 | order does not exist | pay, orderDetail |
| 201 | dep/arr airport empty | search |
| 203 | departure date empty | search |
| 204 | no data / bad date format | search, verify |
| 205 | **departure date earlier than current time** | search (req #3) |
| 206 | route info empty | search |
| 241 | at least one passenger required | search |
| 529/530/531 | contact email empty / bad / phone empty | order |
| 553 | ancillary offer expired | order |
| 745 | orderId cannot be empty | pay, orderDetail |
| 748 | duplicate payment | pay |

---

## 9. TDD test plan

Red-green per endpoint (pytest + `TestClient`), then an end-to-end chain test.

- **auth:** returns bearer token + expected scope.
- **search:** happy path (3 offers, correct FBA per airline); `airlineIds` filter; backdate → 205;
  bad date → 204; missing route → 206; offerKey stable & decodable.
- **verify:** valid offerKey echoes offer; empty → 101.
- **ancillary:** JT/QZ → 5/10/15 kg; GA → 25/30/35 kg; exactly 3 options; keys reversible.
- **search echo:** request `KNO→CGK` `2026-09-20` ⇒ every offer's segment has `depAirport:"KNO"`,
  `arrAirport:"CGK"`, times on `2026-09-20`; offerKey decodes to the same route/date.
- **order:** 10-digit orderId; **N passengers in ⇒ N passengers out (verbatim, same order)**; contacts echoed;
  ancillary key resolution; total math (× pax count); email/phone validation.
- **pay:** UNPAID→ISSUED; ticketNumber (13 digit) per pax; duplicate → 748; unknown order → 148.
- **orderDetail:** returns stored order; same offerKey as search (req #5); unknown → 148.
- **e2e:** search → grab offerKey → verify → ancillary → order (with baggage) → pay → orderDetail;
  assert offerKey identity end-to-end and status transitions.

---

## 10. Decision log

| Decision | Alternatives considered | Why |
|---|---|---|
| FastAPI (Python) | Go | Non-Go org; onboarding Go is high-friction. Pydantic maps 1:1 to the nested/nullable contract; fast TDD loop; perf irrelevant for a mock. |
| Core happy path only (7 endpoints) | Full 9 incl. cancel + getseat | Smaller v1; cancel/seat additive later. Covers req #5 chain. |
| Single flight per airline | Few / richer schedules | Simplest inventory that still exercises the full chain and all 3 airlines. |
| In-memory order store | SQLite | Mock; restart-loss acceptable; zero setup. |
| Deterministic stateless offerKey | Stateful key in store | Guarantees search→orderDetail identity (req #5) with no shared state; survives restarts. |
| Backdate → result code 205 | Empty offers 200 | User chose explicit rejection; 205 is the exact contract code. |
| 3 CHECKEDBAGGAGE options | 5 / cap-at-40 | User chose lighter response. |
| Auth issued but unenforced | Full validation / full stub | User: ignore auth in v1; keep token endpoint so the client's auth step still works. |
| Success envelope `code:0` | HTTP-status-as-code | Confirmed from live samples (`{'code':0,'msg':'success'}`). |

---

## 11. Open items for v2 (not now)

- `cancel` + `getseat` endpoints.
- Round-trip (`routeIndex: -1`) and multi-route search.
- Configurable inventory (schedules/prices via config file).
- Optional auth enforcement toggle.
- Persistence (SQLite) if this becomes a shared long-running service.
