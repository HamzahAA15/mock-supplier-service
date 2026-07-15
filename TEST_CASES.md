# Test Cases — Search → Booking → Issuance

Test-case **specification** (Given/When/Then + assertions) for the end-to-end supplier flow.
This is the blueprint the pytest suite implements once the service is built.
Companion to `DESIGN.md` (behavior) and `API_SCHEMAS.md` (wire shapes).

- "Booking" = the `order` step (creates an `UNPAID` order with an `orderId`).
- "Issuance" = the `pay` step (transitions the order to `ISSUED` and mints tickets),
  verified via `orderDetail`.
- Success envelope for every business call: `code == 0` and `msg == "success"`.

Canonical fixture for this document:
- Route **KNO → CGK**, departure **2026-09-20** (a future date), one-way.
- Booked airline **GA** (chosen because its FBA is 20 kg, so the baggage-ancillary path is meaningful).
- Passengers: **2 ADT** (golden case). A 3-passenger variation is covered in §V1.

---

## TC-E2E-01 — Full happy path (search → book → issue)

**Goal:** a single order flows cleanly from search to an issued ticket, with the correct data
echoed and the correct state transitions.

### Step 0 — Authorize
- **When:** `POST /uaa/oauth/token` with `{ "grantType": "clientCredentials" }`.
- **Then:**
  - HTTP 200; body has non-empty `accessToken`, `tokenType == "Bearer"`, `expiresIn > 0`.
  - `scope` contains `search preOrderVerify ancillarySearch order pay orderDetail`.
- Capture `accessToken` (informational only — v1 does not enforce it).

### Step 1 — Search
- **When:** `POST /flight/search/v3`
  ```json
  {
    "product": ["BASIC"],
    "nonstop": false,
    "routes": [ { "cabin": ["Y"], "oriAirport": "KNO", "destAirport": "CGK", "depDate": "2026-09-20" } ],
    "adultNumber": 2, "childNumber": 0, "infantNumber": 0,
    "airlineIds": ["JT", "GA", "QZ"]
  }
  ```
- **Then:**
  - `code == 0`, `msg == "success"`, `data.currency == "USD"`.
  - `data.offers` has **exactly 3** entries; the set of marketing carriers across `data.segments`
    is exactly `{JT, GA, QZ}`.
  - **Route/date echo (req #1, #2):** every segment has `depAirport == "KNO"`, `arrAirport == "CGK"`,
    and `depTime`/`arrTime` start with `"2026-09-20"`.
  - **FBA per airline (req #8):** the `FREECHECKEDBAGGAGE` ancillary linked to JT and QZ offers has
    `ancillaryCode == 0`; the one linked to the GA offer has `ancillaryCode == 20`.
  - Every offer has `product == ["BASIC"]` (req #4) and a non-empty `offerKey`.
  - Each `charges` entry for the GA offer: `ADT/FARE == 95.00`, `ADT/TAX == 12.00`.
- Capture `gaOfferKey` = the offerKey of the offer whose segment `flightNumber == "GA200"`.

### Step 2 — PreOrderVerify
- **When:** `POST /flight/preOrderVerify/v3` with `{ "offerKey": gaOfferKey }`.
- **Then:**
  - `code == 0`.
  - `data.offers` has 1 entry, and `data.offers[0].offerKey == gaOfferKey` (**offerKey identity**, req #5).
  - `data.segments[0]` still reads `KNO → CGK` on `2026-09-20` (echo preserved through verify).

### Step 3 — AncillarySearch
- **When:** `POST /flight/ancillary/search/v3` with `{ "offerKey": gaOfferKey }`.
- **Then:**
  - `code == 0`.
  - `data.ancillaryOffers` has **exactly 3** `CHECKEDBAGGAGE` options.
  - Because GA FBA is 20 kg, the `ancillaryCode` values are exactly `[25, 30, 35]` (req #9,
    multiples of 5 above FBA); each has `unitOfMeasurement == "WEIGHT"`, `flightNumber == "GA200"`,
    `oriAirport == "KNO"`, `destAirport == "CGK"`.
- Capture `bag25Key` = the `ancillaryKey` of the 25 kg option (expected `1_0_0$GA200$PA25`). The
  `ancillaryKey` is **stateless** and its `adt_chd_inf` prefix is cosmetic — fixed at `1_0_0`, not
  derived from the searched passenger counts (the stateless `offerKey` carries no counts). Assert only
  the stable `$GA200$PA25` suffix; the prefix does not vary with pax.

### Step 4 — Order (booking)
- **When:** `POST /flight/order/v3`
  ```json
  {
    "offerKey": "<gaOfferKey>",
    "ancillaryKeyLists": [ { "passengerIndex": 0, "ancillaryKeys": ["<bag25Key>"] } ],
    "passengers": [
      { "firstName": "BUDI", "lastName": "SANTOSO", "passengerType": "ADT", "sex": "M", "birthDay": "1990-01-15", "nationality": "ID" },
      { "firstName": "SITI", "lastName": "SANTOSO", "passengerType": "ADT", "sex": "F", "birthDay": "1992-03-20", "nationality": "ID" }
    ],
    "contacts": [
      { "contactType": "AG", "firstName": "BUDI", "lastName": "SANTOSO", "email": "agent@example.com", "phone": "+62-8110000000" }
    ]
  }
  ```
- **Then:**
  - `code == 0`.
  - `data.orderId` matches `^\d{10}$` (**10-digit**, req #6).
  - `data.expireInMinutes == 30`; `data.product == ["BASIC"]`; `data.currency == "USD"`.
  - **Passenger echo (req #7):** the order's stored passengers equal the 2 submitted, in order
    (verified fully in Step 6). `data.addedAncillary` has 1 entry for `passengerIndex == 0` containing
    a `CHECKEDBAGGAGE` of `ancillaryCode == 25`, `price == 37.50`.
  - **Total math:** `data.total == 251.50`  = `2 × (95.00 FARE + 12.00 TAX)` + `37.50` baggage.
- Capture `orderId`.

### Step 5 — Pay (issuance)
- **When:** `POST /flight/pay/v3` with `{ "orderId": orderId, "payType": "BPA" }`.
- **Then:**
  - `code == 0`.
  - `data.amount == "251.50"`, `data.currency == "USD"`, `data.transactionId` non-empty.

### Step 5b — Pay with wallet payType (ANTOM/YEEPAY variant)
- **When:** `POST /flight/pay/v3` with `{ "orderId": orderId, "payType": "ANTOM", "accountNumber": "" }`
  (or `"YEEPAY"`; case-insensitive).
- **Then:**
  - `code == 0`; issuance behavior identical to BPA (UNPAID→ISSUED, 13-digit tickets).
  - `data.accountNumber` is the **receiver account** of the wallet-to-wallet transaction
    (`21881200168224D1` for both gateways) even though the request `accountNumber` was empty;
    any payer accountNumber sent in the request is ignored.
  - Subsequent OrderDetail returns the same receiver account in `orderInfo.accountNumber`.

### Step 6 — OrderDetail (verify issuance)
- **When:** `POST /flight/orderDetail/v3` with `{ "orderId": orderId }`.
- **Then:**
  - `code == 0`.
  - `data.orderInfo.status == "ISSUED"` (**state transition** UNPAID→ISSUED); `payTime` non-empty;
    `amount == "251.50"`; `product == ["BASIC"]`.
  - `data.pnrs[0].pnr` matches `^[A-Z0-9]{6}$`; `data.pnrs[0].email == "agent@example.com"`.
  - Each `data.pnrs[0].passengers[*].ticketNumber` matches `^\d{13}$` (**13-digit ticket per pax**),
    and there are 2 of them.
  - **Passenger echo (req #7):** `data.passengerList` equals the 2 submitted passenger objects, in order
    (firstName, lastName, passengerType, sex, birthDay, nationality all match).
  - **Route/date echo end-to-end:** `data.segments[*]` read `KNO → CGK` with `flightNumber == "GA200"`.
  - `data.ancillaryList` contains the 25 kg `CHECKEDBAGGAGE` tied to `SANTOSO/BUDI`.

**Pass criteria:** all six steps return `code == 0` and every assertion above holds.

---

## Key-variation cases (build on TC-E2E-01)

### V1 — Multi-passenger echo (3 pax, req #7)
- **Given** the same flow, but Step 4 submits **3 passengers** (2 ADT + 1 CHD: `SANTOSO/BUDI`,
  `SANTOSO/SITI`, `SANTOSO/AGUS` [CHD, birthDay 2018-07-01]).
- **Then** Step 6 `data.passengerList` has **length 3**, same names/types/order; `pnrs[0].passengers`
  lists 3 entries as `SANTOSO/BUDI`, `SANTOSO/SITI`, `SANTOSO/AGUS`, each with a 13-digit ticket.
- Total includes the child fare per the design's pax-type rule (child = 75% of adult); exact figure
  asserted once the fare rule is finalized in code — see Open item (a).

### V2 — All-airline inventory + FBA (req #1, #8)
- **Given** Step 1 with `airlineIds` omitted.
- **Then** still exactly 3 offers `{JT, GA, QZ}`; JT & QZ free-baggage `ancillaryCode == 0`,
  GA `== 20`. With `airlineIds: ["GA"]` → exactly 1 offer (GA).

### V3 — offerKey identity through the whole chain (req #5)
- **Then** the `offerKey` captured in Step 1 is byte-for-byte identical in the PreOrderVerify request,
  the AncillarySearch request, and the Order request; and decoding it yields
  `airline=GA, ori=KNO, dest=CGK, depDate=2026-09-20, product=BASIC`. OrderDetail segments match.

### V4 — JT/QZ baggage ladder (req #9, FBA 0)
- **Given** the flow booked on **JT** instead of GA.
- **Then** AncillarySearch returns `ancillaryCode` values exactly `[5, 10, 15]` (multiples of 5 above FBA 0),
  and the booked JT offer's free baggage is `0`.

---

## Negative assertions (guardrails, optional in v1)

| Case | Request | Expected |
|---|---|---|
| Backdate search (req #3) | Search with `depDate` before today | `code == 205` |
| Empty offerKey | PreOrderVerify `{ "offerKey": "" }` | `code == 101` |
| Missing contact email | Order with `contacts[0].email == ""` | `code == 529` |
| Duplicate payment | Pay the same `orderId` twice | 2nd call `code == 748` |
| Unknown order | OrderDetail with a non-existent `orderId` | `code == 148` |

---

## Requirements coverage

| Req | Covered by |
|---|---|
| 1 all routes return inventory | Step 1, V2 |
| 2 all future dates return inventory | Step 1 (date echo) |
| 3 no backdate inventory | Negative table |
| 4 all BASIC | Step 1, 4, 6 |
| 5 same offerKey search→orderDetail | Step 2, V3 |
| 6 10-digit orderId | Step 4 |
| 7 echo passenger details | Step 4, 6, V1 |
| 8 JT/QZ FBA 0, GA 20 | Step 1, V2 |
| 9 ancillary multiples of 5 above FBA | Step 3, V4 |

---

## Open items to finalize before coding the suite

- **(a) Child/infant fare rule** — design says child = 75%, infant = 10% of adult fare. Confirm whether
  the pax-type multiplier also applies to `TAX`. TC-E2E-01 avoids this by using 2 adults; V1's exact
  total is pending this decision. (The golden `251.50` is unaffected.)
- **(b) ancillaryKey pax prefix** — RESOLVED: the `offerKey` and `ancillaryKey` are **stateless**, so the
  `<adt>_<chd>_<inf>` prefix is **not** derived from searched pax counts. It is fixed at `1_0_0` (cosmetic).
  The earlier expectation of `2_0_0` for a 2-adult search was a mistake in this doc — tests assert only the
  `$<flight>$PA<kg>` suffix.

---

## Second Baggage — TSY BPI (tsy-bpi contract)

> **Variant: TSY BPI.** These cases cover the **TSY BPI** version (`tsy-bpi`) — paths
> `/secondBaggage`, `/orderCrossSecondBaggage`, `/ancillaryOrderDetail`. The second BPI version
> (**Standardized BPI**) has its own section below.

Separate flow from the flight chain above: `search → order → orderDetail`, **no pay step**
(a successful order is already paid). Envelope is `status: "0"` (string) / `msg: "success"`.
Fixture: segment `VJ VJ84 BNE→SGN`, 1 ADT `TESTER/ALPHA` (synthetic). Design: [`BPI_DESIGN.md`](./BPI_DESIGN.md).

### TC-SB-01 — Full chain

1. **Search** `POST /secondBaggage` with `segments[]` (passenger ignored). Then:
   - `status == "0"`, `msg == "success"`, `auxiliaryOrderNo == null`.
   - one `products[]` per RQ segment; each has **9** `productItems` (weights `[20,30,40,50,60,70,80,90,100]`,
     prices `52.14…536.74`), `productType 1`, `saleType 2`, `baggagePieces 1`, `isAllWeight true`.
   - `segment` echoed + enriched (`cabin:"B"`, `cabinGrade:"Y"`, `tripType:"1"`).
   - `productItemId` = standard base64 of sha256 (deterministic, stateless). Capture the 70kg tier.
2. **Order** `POST /orderCrossSecondBaggage` with client `ancillaryOrderNo` + `passengerAuxes[]`
   (each = `passengerInfo` + `segmentProducts{segment, productItem}` from search). Then:
   - `status == "0"`, `auxiliaryOrderNo` **echoed** (never server-generated).
   - the order's `productItemId` is re-derived from its RQ segment+weight and must match.
   - **Encrypted body + response:** the client sends the whole body AES/CBC-encrypted + base64 (key =
     IV = `B@4p6aay&)*^M0^r`); the server decrypts first, then falls back to plaintext JSON. When the
     request was encrypted, the **response is encrypted the same way** (symmetric); plaintext in →
     plaintext out.
3. **OrderDetail** `POST /ancillaryOrderDetail` with `{auxiliaryOrderNo}`. Then:
   - `data.orderStatus == "PURCHASED"` (always, immediately), `totalPrice` = Σ ordered basePrice.
   - `segments[].arrTime == null`; `passengerAncillaries[].segmentId` links to `segments[].id`;
     `passengerName` = `"Last/First"`, `baggageWeight` = `str(kg)`, `pnrNo` = pax `pnrCode`.

### Second Baggage variations & negatives

| Case | Request | Expected |
|---|---|---|
| Per-segment products | Search with 2 segments | 2 `products[]`, distinct `productItemId` per segment |
| Passenger tolerance | Search with missing/empty/blank passenger | still `status "0"`, full 9-tier catalog |
| Idempotent re-order | Order same `auxiliaryOrderNo` twice (different tier) | both `status "0"`; latest wins in orderDetail |
| Invalid productItemId | Order with tampered `productItemId` | `{auxiliaryOrderNo: null, status: "1"}` |
| Mismatched weight | Order id for 20kg but `baggageAllowance: 30` | `status "1"` (re-derivation fails) |
| Empty auxiliaryOrderNo | Order without `ancillaryOrderNo`/`orderNo` | `status "1"` |
| **Blocked route** | Order a segment `SIN→KUL` or `SIN→CGK` | **HTTP 500**, `msg` names the route; order not created |
| Allowed reverse route | Order a segment `KUL→SIN` | `status "0"` (only `SIN→KUL`/`SIN→CGK` blocked) |
| **Encrypted order body** | Order with AES/CBC+base64 body (key=IV=`B@4p6aay&)*^M0^r`) | decrypts, `status "0"`; **response encrypted too** (symmetric); business rules still apply |
| Plaintext fallback | Order with plaintext JSON body | still `status "0"` (accept-both) |
| Unparseable body | Order with a body that is neither valid AES nor JSON | `{auxiliaryOrderNo: null, status: "1", msg: "invalid request body"}` |
| Unknown order | OrderDetail with unknown `auxiliaryOrderNo` (incl. after restart) | `{status: "1", msg: "order not found", data: null}` |

---

## Standardized BPI (Standardized Ancillary Post-Issuance contract)

> **Variant: Standardized BPI.** Same second-baggage behaviour as TSY BPI, different contract —
> paths `POST /ancillary/v1/baggage/search`, `POST /ancillary/v1/orders`,
> `GET /ancillary/v1/orders/{ancillaryOrderNo}`. Contract source: PRD "Standardized 3PS Baggage
> Post Issuance Automation" §V. Design: [`STANDARDIZED_BPI_DESIGN.md`](./STANDARDIZED_BPI_DESIGN.md).

Envelope is `{code: int, msg, data}`, always HTTP 200 (errors are envelope codes, not HTTP errors).
Plain JSON body; `Authorization` header accepted but never validated. No pay step: order RS returns
`ISSUING`, orderDetail always returns `ISSUED` (Traveloka polls until status change).
Fixture: segment `AK AK342 CGK→BKI` (future `yyyy-MM-dd HH:mm:ss` datetimes), synthetic pax
`TESTER/ALPHA` (`passengerId 1`, `pnr TEST01`).

### TC-SBPI-01 — Full chain

1. **Search** `POST /ancillary/v1/baggage/search` with `ancillaryType: "CHECKEDBAGGAGE"`,
   `routes[].segments[]`, `passengers[]`. Then:
   - `code == 0`, `msg == "Success"`, `data.currency == "USD"`.
   - one `data.routes[]` per RQ route; RQ segments echoed verbatim.
   - passengers present → `passengerOffers[]` (one per pax, `passengerId` echoed), each with
     **9** `ancillaryOffers` (`ancillaryCode` `[20,30,40,50,60,70,80,90,100]` kg, prices
     `52.14…536.74` — same shared tiers as TSY BPI), `ancillaryType CHECKEDBAGGAGE`,
     `ancillaryPiece 1`, `unitOfMeasurement WEIGHT`.
   - `ancillaryKey` is opaque, self-describing (base64url; encodes tripType + segments + weight),
     unique per (route, tier), identical across passengers. Capture the 20kg key.
2. **Order** `POST /ancillary/v1/orders` with client-generated `ancillaryOrderNo`, `isCross`,
   `passengers[]`, `selectedAncillary[] = {passengerId, ancillaryKey}`. Then:
   - `code == 0`, `data.ancillaryOrderNo` **echoed**, `data.orderStatus == "ISSUING"`.
   - `data.total` = Σ tier prices; `createdTime`/`updatedTime` in `yyyy-MM-dd HH:mm:ss`.
   - each `selectedAncillary[]` item carries `ancillaryType/ancillaryCode/ancillaryPiece/price`
     and `segments[]` **reconstructed from the decoded ancillaryKey** (order RQ has no segments).
3. **OrderDetail** `GET /ancillary/v1/orders/{ancillaryOrderNo}`. Then:
   - `code == 0`, `data.orderStatus == "ISSUED"` (always, immediately; repeatable across polls).
   - items additionally carry `unitOfMeasurement: "WEIGHT"`; `total`/`passengers` consistent
     with the order RS.

### Standardized BPI variations & negatives

| Case | Request | Expected |
|---|---|---|
| Pre-issuance live fetch | Search **without** `passengers` | `generalOffers[]` instead of `passengerOffers[]`; same 9 tiers; keys still orderable later |
| Multi-route / multi-pax | Search 2 routes × 2 pax; order different tiers per pax | keys differ per route; `total` = Σ prices; 2 `selectedAncillary[]` items |
| Multi-segment route | Search a 2-segment route | one key per (route, tier); decoded key reconstructs **all** segments |
| Idempotent re-order | Order same `ancillaryOrderNo` twice (different tier) | both `code 0`; latest wins in orderDetail |
| Unsupported ancillaryType | Search with `ancillaryType: "SEAT"` | `code 555`, `data null` |
| Empty routes | Search with `routes: []` | `code 555`, `data null` |
| **Blocked route** | Search or order-key for `SIN→KUL` / `SIN→CGK` | `code 555`, `data null` (HTTP 200 — unlike TSY's HTTP 500) |
| Allowed reverse route | Search `KUL→SIN` | `code 0` (blocklist is directional) |
| **Past departure** | Search a segment with past `departureTime` | `code 5001` "prohibition of sale before or after departure" |
| Invalid ancillaryKey | Order with forged/tampered key, or non-tier weight | `code 400` "invalid ancillaryKey"; order not created |
| Unknown passengerId | Order item referencing a pax not in `passengers[]` | `code 400` |
| Missing ancillaryOrderNo | Order without `ancillaryOrderNo` | `code 400` "invalid ancillary order number" |
| Empty selectedAncillary | Order with `selectedAncillary: []` | `code 400` |
| Unknown order | OrderDetail GET with unknown order no (incl. after restart) | `code 400`, `data null` |
| Version coexistence | TSY and Standardized endpoints in the same run | both respond per their own envelope (`status "0"` vs `code 0`) |
