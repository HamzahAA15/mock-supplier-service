# Second Baggage Mock (TSY BPI) — Implementation Plan

Status: **Implemented** · Owner: Hamzah Alfauzi · Date: 2026-07-08

> **Variant: TSY BPI.** This document and the three endpoints below
> (`/secondBaggage`, `/orderCrossSecondBaggage`, `/ancillaryOrderDetail`) — and all their
> logic — implement the **TSY BPI** version of second baggage (`tsy-bpi` contract). A second
> BPI version (e.g. `standardizedv3-bpi`) is planned and will be added separately with its own
> paths/logic; anything labeled "TSY BPI" here is specific to this variant.

Adds the TSY-native second-baggage flow (`search → order → orderDetail`) to the
existing mock supplier FastAPI app. Contract source: `bpi-rq-rs/tsy-bpi/*.json`.
(Internally still referenced as "BPI"; the file/module names keep that shorthand.)

---

## 1. Confirmed decisions

1. **Contract:** **TSY BPI** (`tsy-bpi`) only (`status:"0"` string envelope). The other BPI
   version (`standardizedv3-bpi`) is out of scope here and will be its own implementation.
2. **Placement:** new router in the existing app (`app/routers/bpi.py`), reusing repo patterns.
3. **Paths (confirmed):** search `POST /secondBaggage`, order `POST /orderCrossSecondBaggage`,
   orderDetail `POST /ancillaryOrderDetail`.
4. **Payment model:** there is no pay step. A successful `order` means payment is done;
   `orderDetail` thereafter returns `orderStatus: "PURCHASED"` — always, immediately.
5. **auxiliaryOrderNo:** client-supplied in order RQ (`ancillaryOrderNo`/`orderNo`); mock stores
   under it and echoes it back. Never server-generated.
6. **Validation:** `order` validates `productItemId` by re-deriving it from the RQ segment +
   baggage tier (see §4). Unknown/mismatched ID → generic failure. All other inputs: happy path only.
7. **Errors (generic failure only):** HTTP 200 with
   - order: `{"auxiliaryOrderNo": null, "msg": "<reason>", "status": "1"}`
   - orderDetail (unknown auxiliaryOrderNo, incl. after restart): `{"status": "1", "msg": "order not found", "data": null}`
11. **Blocked routes (order):** segments on the routes **SIN→KUL** or **SIN→CGK** (directional:
    dep `SIN`, arr `KUL`/`CGK`) are not eligible for second baggage. Ordering such a segment fails
    the order with **HTTP 500** and body `{"auxiliaryOrderNo": null, "status": "1", "msg": "second
    baggage not available for route <dep>-<arr>"}` — the order is not created. (Deliberate exception
    to the HTTP-200 rule in §7, per product requirement.) Search is unaffected. Constant lives in
    `app/services/bpi_catalog.py::BLOCKED_SECOND_BAGGAGE_ROUTES`.
12. **Encrypted order body + response (order only):** the client encrypts the
    `/orderCrossSecondBaggage` request body with **AES/CBC/PKCS5Padding** and **standard base64**;
    the whole HTTP body is that base64 string. Key = `B@4p6aay&)*^M0^r` (16 bytes, AES-128),
    **IV = the key bytes** (`IvParameterSpec(key.getBytes())`). The server decrypts, then parses JSON.
    **Accept-both:** if decryption fails, the body is treated as plaintext JSON (keeps tests / manual
    curl working); unparseable → `{"auxiliaryOrderNo": null, "status": "1", "msg": "invalid request body"}`.
    **Symmetric response:** when the request was encrypted, the **response body is encrypted too**
    (same key/IV/mode, base64 string, `Content-Type: text/plain`) — for **all** outcomes: success,
    business-failure envelopes (`status "1"`), and the blocked-route **HTTP 500**. A plaintext request
    gets a plaintext JSON response. Only this endpoint is encrypted; `/secondBaggage` and
    `/ancillaryOrderDetail` stay plaintext. Logic in `app/services/crypto.py` (key overridable via
    `SECOND_BAGGAGE_AES_KEY`). Known-answer vector for Java cross-check:
    `encrypt("hello world") == "b4veAzBq4t5O8dJ+h1Q21Q=="`.
8. **Auth:** none, same as existing v1 endpoints.
9. **Search passengers:** the `passenger` array may be missing, empty, or have empty-string
   fields; search ignores it entirely — the response depends only on `segments`.
10. **Tests:** pytest per endpoint + e2e, extend Postman collection, update TEST_CASES.md.

---

## 2. Flow

```
search (segments[, passengers]) ──► 9 baggage tiers per segment (productItemId per tier)
order  (auxOrderNo + passengerAuxes: segment + chosen productItem) ──► success ⇒ paid
orderDetail ({auxiliaryOrderNo}) ──► orderStatus: PURCHASED
```

## 3. Catalog (fixed, from sample)

9 tiers, `productType 1`, `saleType 2`, `baggagePieces 1`, `isAllWeight true`, `currency USD`,
refundRule all-false with `"*"` rules:

| kg | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 |
|----|----|----|----|----|----|----|----|----|-----|
| USD | 52.14 | 76.84 | 103.18 | 256.30 | 307.33 | 358.38 | 430.27 | 483.49 | 536.74 |

Returned for **any** segment (any carrier/route/date), one `products[]` entry per RQ segment,
echoing the segment enriched with the static extra fields seen in the sample
(`cabin:"B"`, `cabinGrade:"Y"`, `codeShare:false`, empty terminals, `tripType` as string, etc.).

## 4. productItemId — deterministic, stateless

Same philosophy as the existing `offer_key` service:

```
productItemId = base64( sha256(f"{carrier}|{flightNumber}|{depAirport}|{depTime}|{arrAirport}|{arrTime}|{weightKg}|BPI") )
```

(Standard base64 — matches the sample's `+`/`/`/`=` format, confirmed 2026-07-08. The mock's IDs are
deterministic and round-trip search→order, but are **not** byte-identical to the recorded sample IDs,
whose original hash input is unknown.)

- Search derives IDs on the fly; no state.
- Order re-derives from its own RQ (`segmentProducts.segment` + `productItem.baggage.baggageAllowance`)
  and compares with the RQ's `productItemId`. Mismatch → generic failure (§1.7).
- Restart-tolerant: order works without a prior search on the same process.

## 5. Order store & orderDetail

- In-memory dict keyed by `auxiliaryOrderNo` (consistent with existing `orders.py`; lost on restart — acceptable).
- Same `auxiliaryOrderNo` ordered twice → idempotent upsert (latest wins, still `status:"0"`).
- Stored per order: passengerAuxes, per-segment deterministic numeric `id`
  (`crc32` of segment key — stable across restarts within the response only), totals.
- `orderDetail` RS mapping (per sample):
  - `orderStatus`: `"PURCHASED"`
  - `totalPrice`: sum of ordered `basePrice`
  - `segments[]`: from stored order; `arrTime` may be null per sample
  - `passengerAncillaries[]`: `passengerName` = `"Last/First"`, `baggageWeight` = str(kg),
    `pnrNo`, `segmentId` → matching segment `id`

## 6. File changes

| File | Change |
|---|---|
| `app/models/bpi.py` | Pydantic RQ/RS models for all three endpoints (passenger fields optional/empty-tolerant) |
| `app/services/bpi_catalog.py` | tier table + productItemId derivation |
| `app/services/bpi_orders.py` | in-memory store, segment-id generation, totals |
| `app/routers/bpi.py` | the three endpoints (paths per §1.3) |
| `app/main.py` | `include_router(bpi.router)` |
| `tests/test_bpi_search.py` | shapes, 9 tiers, per-segment products, empty/missing passengers |
| `tests/test_bpi_order.py` | happy path, echo auxOrderNo, invalid productItemId → status "1", idempotent re-order |
| `tests/test_bpi_order_detail.py` | PURCHASED, totals, segmentId linkage, unknown order → status "1" |
| `tests/test_bpi_e2e.py` | search → order → orderDetail chained |
| Postman collection | new BPI folder, chained via collection vars, assertions incl. negative ID case |
| `TEST_CASES.md` | BPI test-case section |
| `README.md` / `DESIGN.md` | mention BPI flow + link here |

## 7. Build order (TDD, red-green per endpoint)

1. `bpi_catalog` service + unit tests (derivation determinism).
2. `search` endpoint (models → tests → impl).
3. `order` (store, validation, failure envelope).
4. `orderDetail` (PURCHASED, not-found envelope).
5. e2e pytest, Postman folder, TEST_CASES.md, doc updates.

## 8. Out of scope (v1)

Auth enforcement, cancel/refund of ancillary orders, INF/CHD-specific rules, overweight
(`supportOverWeight` stays false), non-baggage productTypes, cross-restart persistence,
Pending/async status simulation, standardizedv3 contract.
