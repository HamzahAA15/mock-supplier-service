# Mock Supplier Service

A FastAPI service that mimics a Traveloka flight **supplier** (partner API server).
It returns deterministic, schema-shaped mock inventory across the core booking chain
(`token → search → preOrderVerify → ancillarySearch → order → pay → orderDetail`) so the
aggregator can be integration-tested without a real airline backend.

It also mocks the TSY-native **Baggage Post-Issuance (BPI)** flow
(`/postBaggage → /orderCrossPostBaggage → /ancillaryOrderDetail`) — a separate
`status:"0"`-envelope contract with no pay step (a successful order is already paid).

Design: [DESIGN.md](DESIGN.md) · Wire shapes: [API_SCHEMAS.md](API_SCHEMAS.md) · BPI: [BPI_DESIGN.md](BPI_DESIGN.md)

## Setup & run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000
```

Interactive docs at `http://localhost:8000/docs`.

## Test

```bash
.venv/bin/python -m pytest
```

## Postman / Newman (end-to-end API tests)

[`mock-supplier-service.postman_collection.json`](mock-supplier-service.postman_collection.json)
covers the full [TEST_CASES.md](TEST_CASES.md) spec (TC-E2E-01 + variations V1/V2/V4 + negative
assertions): 22 requests, 61 assertions. It chains values (offerKey, orderId, …) automatically via
collection variables, so it runs top-to-bottom. Import it into Postman, or run it headless with Newman.

Start the server first (`.venv/bin/uvicorn app.main:app --port 8000`), then in another shell:

```bash
# plain run (terminal summary)
newman run mock-supplier-service.postman_collection.json
```

Point it at a different host by overriding the `baseUrl` collection variable:
`newman run ... --env-var baseUrl=http://some-host:8000`.

### HTML report

Newman's HTML output needs a reporter plugin (install once):

```bash
npm install -g newman-reporter-htmlextra
```

Then run with both the CLI and HTML reporters — you get the live terminal summary *and* a shareable file:

```bash
newman run mock-supplier-service.postman_collection.json \
  -r cli,htmlextra \
  --reporter-htmlextra-export reports/newman-report.html \
  --reporter-htmlextra-title "Mock Supplier Service — TEST_CASES.md"

open reports/newman-report.html   # macOS; or just double-click the file
```

The report has a pass/fail dashboard plus per-request sent/received bodies and assertions. Generated
reports land in `reports/` (git-ignored). For a lighter-weight report use the basic reporter instead
(`npm install -g newman-reporter-html`, then `-r html --reporter-html-export reports/basic-report.html`).

## Quick chain (curl)

```bash
BASE=http://localhost:8000

# 1. token (dummy, unenforced in v1)
curl -s $BASE/uaa/oauth/token -H 'Content-Type: application/json' \
  -d '{"grantType":"clientCredentials"}'

# 2. search — any route, any future date; returns JT/GA/QZ offers
curl -s $BASE/flight/search/v3 -H 'Content-Type: application/json' -d '{
  "product":["BASIC"],"nonstop":false,
  "routes":[{"cabin":["Y"],"oriAirport":"CGK","destAirport":"DPS","depDate":"2026-09-20"}],
  "adultNumber":1,"childNumber":0,"infantNumber":0}'

# 3. verify (offerKey from search)
curl -s $BASE/flight/preOrderVerify/v3 -H 'Content-Type: application/json' \
  -d '{"offerKey":"<offerKey>"}'

# 4. baggage options (multiples of 5 kg above the airline FBA)
curl -s $BASE/flight/ancillary/search/v3 -H 'Content-Type: application/json' \
  -d '{"offerKey":"<offerKey>"}'

# 5. order — passengers/contacts are echoed back verbatim
curl -s $BASE/flight/order/v3 -H 'Content-Type: application/json' -d '{
  "offerKey":"<offerKey>",
  "ancillaryKeyLists":[{"passengerIndex":0,"ancillaryKeys":["<ancillaryKey>"]}],
  "passengers":[{"firstName":"BUDI","lastName":"SANTOSO","passengerType":"ADT",
                 "sex":"M","birthDay":"1990-01-15","nationality":"ID"}],
  "contacts":[{"contactType":"AG","firstName":"BUDI","lastName":"SANTOSO",
               "email":"budi@example.com","phone":"+62-811111111"}]}'

# 6. pay (UNPAID -> ISSUED, mints 13-digit tickets)
curl -s $BASE/flight/pay/v3 -H 'Content-Type: application/json' \
  -d '{"orderId":"<orderId>","payType":"BPA","accountNumber":""}'

# 6b. pay via wallet-to-wallet (ANTOM or YEEPAY): request accountNumber is empty;
#     response accountNumber is the RECEIVER wallet account (21881200168224D1)
curl -s $BASE/flight/pay/v3 -H 'Content-Type: application/json' \
  -d '{"orderId":"<orderId>","payType":"ANTOM","accountNumber":""}'

# 7. order detail
curl -s $BASE/flight/orderDetail/v3 -H 'Content-Type: application/json' \
  -d '{"orderId":"<orderId>"}'
```

## v1 behavior notes

- Every response is HTTP 200; the business result is in the body envelope
  (`code: 0, msg: "success"`), except the token endpoint (no envelope).
- Orders live in memory only — lost on restart. offerKeys are stateless
  (base64url of `AIRLINE|ORI|DEST|DEPDATE|BASIC`) and survive restarts.
- Segments emit **`stopovers`** (guideline field name; decided 2026-07-05).
- FBA `ancillaryPiece` is `0` when the free allowance is 0 kg (JT/QZ), `1` for GA.
- Order `expiredTime` (+30 min) is informational; Pay does not enforce expiry.
- All passenger types share the same baggage arrangement; the `1_0_0` prefix in
  ancillaryKeys is cosmetic.
