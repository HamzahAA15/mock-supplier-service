# API Schemas — Mock Supplier Service

Concrete request/response JSON for all 7 endpoints, using the v1 mock values
(airlines JT/GA/QZ, route `CGK→DPS`, `depDate 2026-07-10`, 1 adult, currency `USD`, product `BASIC`).
Companion to `DESIGN.md` §7. These are the exact wire shapes the coding agent should reproduce.

> **Echo principle (DESIGN §3.1).** The *route*, *departure date*, and *passenger/contact* data in every
> response are echoed from the request — only airline/flight/time/fare/FBA are fixed mock inventory.
> The examples below happen to use `CGK→DPS`; if the request were `KNO→CGK` `2026-09-20`, every segment
> would read `KNO`/`CGK` with times on `2026-09-20`, and an Order with 3 passengers returns 3 passengers.

## Conventions

- All endpoints are `POST`, `Content-Type: application/json`, HTTP status `200`.
- **Business result lives in the body**: `{ "code": int, "msg": string, "data": object }`.
  `code: 0` + `msg: "success"` = success (confirmed from live supplier samples).
- JSON is camelCase. `null` allowed where the contract marks a field nullable.
- Field-name note: segments use **`stopovers`** (array), the guideline's field name —
  confirmed with the owner on 2026-07-05, overriding the live-wire captures which showed
  `stopover`.

## Shared enums / formats

- `passengerType`: `ADT` | `CHD` | `INF`. `cabin`/`seatClass`: `Y` (Economy) in v1.
- `chargeType`: `FARE` | `TAX`. `ancillaryType`: `FREECHECKEDBAGGAGE` | `CHECKEDBAGGAGE`.
- `unitOfMeasurement`: `WEIGHT`. datetimes: `yyyy-MM-dd HH:mm:ss` (local). dates: `yyyy-MM-dd`.
- `orderId`: 10-digit numeric string. `pnr`: 6-char alnum. `ticketNumber`: 13-digit string.
- `offerKey`: `base64url("<AIRLINE>|<ORI>|<DEST>|<DEPDATE>|BASIC")`.
- `ancillaryKey`: `"<adt>_<chd>_<inf>$<flightNumber>$PA<kg>"`, e.g. `1_0_0$GA200$PA25`.

---

## 1. `POST /uaa/oauth/token`

**Request** (header `Authorization: Basic base64(merchId:merchSecret)` — accepted but not validated in v1)
```json
{ "grantType": "clientCredentials" }
```

**Response** (no `code` envelope — matches auth sample)
```json
{
  "accessToken": "b0f3c9a2-7e4d-4a1b-9c88-2f0a1d3e5c77",
  "tokenType": "Bearer",
  "expiresIn": 3600,
  "scope": "search preOrderVerify ancillarySearch order pay orderDetail"
}
```

---

## 2. `POST /flight/search/v3`

**Request**
```json
{
  "product": ["BASIC"],
  "nonstop": false,
  "routes": [
    { "cabin": ["Y"], "oriAirport": "CGK", "destAirport": "DPS", "depDate": "2026-07-10" }
  ],
  "adultNumber": 1,
  "childNumber": 0,
  "infantNumber": 0,
  "airlineIds": ["JT", "GA", "QZ"]
}
```

**Success response** (3 offers — one per airline; offers/flights/ancillaries linked by index)
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "currency": "USD",
    "offers": [
      {
        "offerKey": "SlR8Q0dLfERQU3wyMDI2LTA3LTEwfEJBU0lD",
        "routeIndex": 0,
        "product": ["BASIC"],
        "issuanceTimeInMins": 120,
        "serviceFeePerPax": null,
        "cheapestOption": false,
        "flightRefs": [{ "flightIndex": 0 }],
        "charges": [
          { "passengerType": "ADT", "chargeType": "FARE", "price": 60.00 },
          { "passengerType": "ADT", "chargeType": "TAX",  "price": 8.00 }
        ],
        "freeAncillaryRefs": [
          { "ancillaryIndex": 0, "passengerType": "ADT", "segmentIndex": 0 }
        ]
      },
      {
        "offerKey": "R0F8Q0dLfERQU3wyMDI2LTA3LTEwfEJBU0lD",
        "routeIndex": 0,
        "product": ["BASIC"],
        "issuanceTimeInMins": 120,
        "serviceFeePerPax": null,
        "cheapestOption": false,
        "flightRefs": [{ "flightIndex": 1 }],
        "charges": [
          { "passengerType": "ADT", "chargeType": "FARE", "price": 95.00 },
          { "passengerType": "ADT", "chargeType": "TAX",  "price": 12.00 }
        ],
        "freeAncillaryRefs": [
          { "ancillaryIndex": 1, "passengerType": "ADT", "segmentIndex": 1 }
        ]
      },
      {
        "offerKey": "UVp8Q0dLfERQU3wyMDI2LTA3LTEwfEJBU0lD",
        "routeIndex": 0,
        "product": ["BASIC"],
        "issuanceTimeInMins": 120,
        "serviceFeePerPax": null,
        "cheapestOption": true,
        "flightRefs": [{ "flightIndex": 2 }],
        "charges": [
          { "passengerType": "ADT", "chargeType": "FARE", "price": 55.00 },
          { "passengerType": "ADT", "chargeType": "TAX",  "price": 7.00 }
        ],
        "freeAncillaryRefs": [
          { "ancillaryIndex": 2, "passengerType": "ADT", "segmentIndex": 2 }
        ]
      }
    ],
    "flights": [
      {
        "segmentRefs": [{ "segmentIndex": 0, "seatClass": "Y", "cabin": "Y", "seatCount": 9 }],
        "transferCount": 0,
        "transfer": [],
        "refundRefs": [
          {
            "routeIndex": 0, "sourcePolicy": "AIRLINE_POLICY", "matchingPaxTypes": ["ALL"],
            "partialPax": true, "partialRoute": "NO",
            "periodAndFees": [
              { "refundable": false, "startPeriodType": "AFTER_PURCHASE", "endPeriodType": "BEFORE_DEPARTURE",
                "startNumHours": 0, "endNumHours": 0, "amount": 0.0, "currencyCode": "USD",
                "isPercentage": false, "refundType": "REGULAR", "flightRefundFeeLevelType": "PER_ROUTE" }
            ],
            "otherInfo": { "cat16Info": "", "cat31Info": "", "cat33Info": "" }
          }
        ],
        "changeRefs": [
          {
            "routeIndex": 0, "sourcePolicy": "AIRLINE_POLICY", "matchingPaxTypes": ["ALL"],
            "partialPax": true, "partialRoute": "NO",
            "periodAndFees": [
              { "changeable": true, "startPeriodType": "AFTER_PURCHASE", "endPeriodType": "BEFORE_DEPARTURE",
                "startNumHours": 0, "endNumHours": 48, "amount": 25.0, "currencyCode": "USD",
                "isPercentage": false, "feeValueType": "PER_ROUTE", "changeType": "REISSUANCE",
                "reasonType": "REGULAR" }
            ],
            "otherInfo": { "cat16Info": "", "cat31Info": "", "cat33Info": "" }
          }
        ]
      },
      {
        "segmentRefs": [{ "segmentIndex": 1, "seatClass": "Y", "cabin": "Y", "seatCount": 9 }],
        "transferCount": 0, "transfer": [],
        "refundRefs": [ { "routeIndex": 0, "sourcePolicy": "AIRLINE_POLICY", "matchingPaxTypes": ["ALL"], "partialPax": true, "partialRoute": "NO", "periodAndFees": [ { "refundable": false, "startPeriodType": "AFTER_PURCHASE", "endPeriodType": "BEFORE_DEPARTURE", "startNumHours": 0, "endNumHours": 0, "amount": 0.0, "currencyCode": "USD", "isPercentage": false, "refundType": "REGULAR", "flightRefundFeeLevelType": "PER_ROUTE" } ], "otherInfo": { "cat16Info": "", "cat31Info": "", "cat33Info": "" } } ],
        "changeRefs": [ { "routeIndex": 0, "sourcePolicy": "AIRLINE_POLICY", "matchingPaxTypes": ["ALL"], "partialPax": true, "partialRoute": "NO", "periodAndFees": [ { "changeable": true, "startPeriodType": "AFTER_PURCHASE", "endPeriodType": "BEFORE_DEPARTURE", "startNumHours": 0, "endNumHours": 48, "amount": 25.0, "currencyCode": "USD", "isPercentage": false, "feeValueType": "PER_ROUTE", "changeType": "REISSUANCE", "reasonType": "REGULAR" } ], "otherInfo": { "cat16Info": "", "cat31Info": "", "cat33Info": "" } } ]
      },
      {
        "segmentRefs": [{ "segmentIndex": 2, "seatClass": "Y", "cabin": "Y", "seatCount": 9 }],
        "transferCount": 0, "transfer": [],
        "refundRefs": [ { "routeIndex": 0, "sourcePolicy": "AIRLINE_POLICY", "matchingPaxTypes": ["ALL"], "partialPax": true, "partialRoute": "NO", "periodAndFees": [ { "refundable": false, "startPeriodType": "AFTER_PURCHASE", "endPeriodType": "BEFORE_DEPARTURE", "startNumHours": 0, "endNumHours": 0, "amount": 0.0, "currencyCode": "USD", "isPercentage": false, "refundType": "REGULAR", "flightRefundFeeLevelType": "PER_ROUTE" } ], "otherInfo": { "cat16Info": "", "cat31Info": "", "cat33Info": "" } } ],
        "changeRefs": [ { "routeIndex": 0, "sourcePolicy": "AIRLINE_POLICY", "matchingPaxTypes": ["ALL"], "partialPax": true, "partialRoute": "NO", "periodAndFees": [ { "changeable": true, "startPeriodType": "AFTER_PURCHASE", "endPeriodType": "BEFORE_DEPARTURE", "startNumHours": 0, "endNumHours": 48, "amount": 25.0, "currencyCode": "USD", "isPercentage": false, "feeValueType": "PER_ROUTE", "changeType": "REISSUANCE", "reasonType": "REGULAR" } ], "otherInfo": { "cat16Info": "", "cat31Info": "", "cat33Info": "" } } ]
      }
    ],
    "segments": [
      { "marketingCarrier": "JT", "flightNumber": "JT100", "operatingCarrier": "JT", "operatingFlightNumber": "JT100",
        "depAirport": "CGK", "arrAirport": "DPS", "depTerminal": "", "arrTerminal": "",
        "depTime": "2026-07-10 08:00:00", "arrTime": "2026-07-10 10:00:00", "codeShare": false,
        "aircraftCode": "B739", "fareBasis": "", "brandedFare": "", "duration": 120, "stopovers": [] },
      { "marketingCarrier": "GA", "flightNumber": "GA200", "operatingCarrier": "GA", "operatingFlightNumber": "GA200",
        "depAirport": "CGK", "arrAirport": "DPS", "depTerminal": "", "arrTerminal": "",
        "depTime": "2026-07-10 12:00:00", "arrTime": "2026-07-10 14:00:00", "codeShare": false,
        "aircraftCode": "B738", "fareBasis": "", "brandedFare": "", "duration": 120, "stopovers": [] },
      { "marketingCarrier": "QZ", "flightNumber": "QZ300", "operatingCarrier": "QZ", "operatingFlightNumber": "QZ300",
        "depAirport": "CGK", "arrAirport": "DPS", "depTerminal": "", "arrTerminal": "",
        "depTime": "2026-07-10 16:00:00", "arrTime": "2026-07-10 18:00:00", "codeShare": false,
        "aircraftCode": "A320", "fareBasis": "", "brandedFare": "", "duration": 120, "stopovers": [] }
    ],
    "ancillaries": [
      { "ancillaryType": "FREECHECKEDBAGGAGE", "ancillaryCode": 0,  "ancillaryPiece": 0, "unitOfMeasurement": "WEIGHT", "desc": "0kg" },
      { "ancillaryType": "FREECHECKEDBAGGAGE", "ancillaryCode": 20, "ancillaryPiece": 1, "unitOfMeasurement": "WEIGHT", "desc": "20kg" },
      { "ancillaryType": "FREECHECKEDBAGGAGE", "ancillaryCode": 0,  "ancillaryPiece": 0, "unitOfMeasurement": "WEIGHT", "desc": "0kg" }
    ]
  }
}
```

**Per-airline offer values** (the parts that differ across the 3 offers above):

| index | airline | offerKey (decoded) | flight/segment idx | FARE | TAX | ancillary idx (FBA kg) |
|---|---|---|---|---|---|---|
| 0 | JT | `JT\|CGK\|DPS\|2026-07-10\|BASIC` | 0 | 60.00 | 8.00 | 0 (0) |
| 1 | GA | `GA\|CGK\|DPS\|2026-07-10\|BASIC` | 1 | 95.00 | 12.00 | 1 (20) |
| 2 | QZ | `QZ\|CGK\|DPS\|2026-07-10\|BASIC` | 2 | 55.00 | 7.00 | 2 (0) |

The full v1 inventory has **6 airlines**. Omitting `airlineIds` returns one offer per airline
(order: JT, GA, QZ, AK, SQ, JL); the example above filters to the first three. The rest:

| index | airline | offerKey (decoded) | FARE | TAX | FBA kg | ancillary ladder (kg) |
|---|---|---|---|---|---|---|
| 3 | AK | `AK\|CGK\|DPS\|2026-07-10\|BASIC` | 50.00 | 6.00 | 0  | 5, 10, 15 |
| 4 | SQ | `SQ\|CGK\|DPS\|2026-07-10\|BASIC` | 120.00 | 15.00 | 20 | 25, 30, 35 |
| 5 | JL | `JL\|CGK\|DPS\|2026-07-10\|BASIC` | 110.00 | 14.00 | 15 | 20, 25, 30 |

`cheapestOption` is on the lowest fare among the *returned* offers — AK (50.00) when all six are returned.

**Error response — backdate (req #3), `depDate < today`**
```json
{ "code": 205, "msg": "The departure date cannot be earlier than the current time", "data": null }
```
Other search errors: `201` airport empty, `203` depDate empty, `204` bad date format, `206` route empty, `241` no adult.

---

## 3. `POST /flight/preOrderVerify/v3`

**Request**
```json
{ "offerKey": "R0F8Q0dLfERQU3wyMDI2LTA3LTEwfEJBU0lD" }
```

**Success response** — same `data` shape as Search, but containing only the single verified offer
(its `offers`, `flights`, `segments`, `ancillaries` arrays each hold just that offer's entry).
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "currency": "USD",
    "offers": [ { "offerKey": "R0F8Q0dLfERQU3wyMDI2LTA3LTEwfEJBU0lD", "routeIndex": 0, "product": ["BASIC"], "issuanceTimeInMins": 120, "serviceFeePerPax": null, "cheapestOption": false, "flightRefs": [{ "flightIndex": 0 }], "charges": [ { "passengerType": "ADT", "chargeType": "FARE", "price": 95.00 }, { "passengerType": "ADT", "chargeType": "TAX", "price": 12.00 } ], "freeAncillaryRefs": [ { "ancillaryIndex": 0, "passengerType": "ADT", "segmentIndex": 0 } ] } ],
    "flights": [ { "segmentRefs": [{ "segmentIndex": 0, "seatClass": "Y", "cabin": "Y", "seatCount": 9 }], "transferCount": 0, "transfer": [], "refundRefs": [], "changeRefs": [] } ],
    "segments": [ { "marketingCarrier": "GA", "flightNumber": "GA200", "operatingCarrier": "GA", "operatingFlightNumber": "GA200", "depAirport": "CGK", "arrAirport": "DPS", "depTerminal": "", "arrTerminal": "", "depTime": "2026-07-10 12:00:00", "arrTime": "2026-07-10 14:00:00", "codeShare": false, "aircraftCode": "B738", "fareBasis": "", "brandedFare": "", "duration": 120, "stopovers": [] } ],
    "ancillaries": [ { "ancillaryType": "FREECHECKEDBAGGAGE", "ancillaryCode": 20, "ancillaryPiece": 1, "unitOfMeasurement": "WEIGHT", "desc": "20kg" } ]
  }
}
```
(refundRefs/changeRefs may reuse the same policy template as Search; shown empty here for brevity.)

**Error — empty offerKey**
```json
{ "code": 101, "msg": "The offerKey cannot be empty", "data": null }
```

---

## 4. `POST /flight/ancillary/search/v3`

**Request**
```json
{ "offerKey": "R0F8Q0dLfERQU3wyMDI2LTA3LTEwfEJBU0lD" }
```

**Success response** — 3 `CHECKEDBAGGAGE` options, multiples of 5 above the airline's FBA.
GA (FBA 20) shown → 25/30/35 kg. (JT/QZ FBA 0 → 5/10/15 kg.) Price = `kg * 1.5` USD (mock rule).
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "currency": "USD",
    "ancillaryOffers": [
      { "addAncillaryType": "CHECKEDBAGGAGE", "ancillaryKey": "1_0_0$GA200$PA25", "ancillaryCode": 25, "ancillaryPiece": 1, "unitOfMeasurement": "WEIGHT", "desc": "25kg", "oriAirport": "CGK", "destAirport": "DPS", "transferAirport": "", "flightNumber": "GA200", "price": 37.50 },
      { "addAncillaryType": "CHECKEDBAGGAGE", "ancillaryKey": "1_0_0$GA200$PA30", "ancillaryCode": 30, "ancillaryPiece": 1, "unitOfMeasurement": "WEIGHT", "desc": "30kg", "oriAirport": "CGK", "destAirport": "DPS", "transferAirport": "", "flightNumber": "GA200", "price": 45.00 },
      { "addAncillaryType": "CHECKEDBAGGAGE", "ancillaryKey": "1_0_0$GA200$PA35", "ancillaryCode": 35, "ancillaryPiece": 1, "unitOfMeasurement": "WEIGHT", "desc": "35kg", "oriAirport": "CGK", "destAirport": "DPS", "transferAirport": "", "flightNumber": "GA200", "price": 52.50 }
    ]
  }
}
```

**JT/QZ example** (FBA 0 → 5/10/15): `ancillaryKey` `1_0_0$JT100$PA5`, codes 5/10/15, prices 7.50/15.00/22.50.

---

## 5. `POST /flight/order/v3`

**Request**
```json
{
  "offerKey": "R0F8Q0dLfERQU3wyMDI2LTA3LTEwfEJBU0lD",
  "ancillaryKeyLists": [
    { "passengerIndex": 0, "ancillaryKeys": ["1_0_0$GA200$PA25"] }
  ],
  "passengers": [
    { "firstName": "CANDY FREDRICK", "lastName": "MURING BALA", "passengerType": "ADT",
      "sex": "M", "birthDay": "1997-06-02", "nationality": "MY" }
  ],
  "contacts": [
    { "contactType": "AG", "firstName": "CANDY FREDRICK", "lastName": "MURING BALA",
      "email": "agent@example.com", "phone": "+62-8110000000" }
  ]
}
```

**Success response** — `orderId` is a fresh random 10-digit string; `total` = FARE+TAX+ancillary = 95+12+37.50.
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "currency": "USD",
    "total": 144.50,
    "orderId": "4820137655",
    "expireInMinutes": 30,
    "product": ["BASIC"],
    "issuanceTimeInMins": 120,
    "serviceFeePerPax": null,
    "addedAncillary": [
      {
        "passengerIndex": 0,
        "passengerName": "MURING BALA/CANDY FREDRICK",
        "ancillaryOffers": [
          { "addAncillaryType": "CHECKEDBAGGAGE", "ancillaryKey": "1_0_0$GA200$PA25", "ancillaryCode": 25, "ancillaryPiece": 1, "unitOfMeasurement": "WEIGHT", "desc": "25kg", "oriAirport": "CGK", "destAirport": "DPS", "transferAirport": "", "flightNumber": "GA200", "price": 37.50 }
        ]
      }
    ],
    "offers": [ "... same single-offer array as preOrderVerify ..." ],
    "penalties": [],
    "ancillaries": [ { "ancillaryType": "FREECHECKEDBAGGAGE", "ancillaryCode": 20, "ancillaryPiece": 1, "unitOfMeasurement": "WEIGHT", "desc": "20kg" } ],
    "flights": [ "... same single-flight array as preOrderVerify ..." ],
    "segments": [ { "marketingCarrier": "GA", "flightNumber": "GA200", "operatingCarrier": "GA", "operatingFlightNumber": "GA200", "depAirport": "CGK", "arrAirport": "DPS", "depTerminal": "", "arrTerminal": "", "depTime": "2026-07-10 12:00:00", "arrTime": "2026-07-10 14:00:00", "codeShare": false, "aircraftCode": "B738", "fareBasis": "", "brandedFare": "", "duration": 120, "stopovers": [] } ]
  }
}
```
Errors: `529` email empty, `530` email bad format, `531` phone empty, `553` ancillary offer expired.

### 5.1 Multi-passenger echo (req #7)

If the request carries 3 passengers, the response carries the same 3, in order, verbatim.

**Request (`passengers` excerpt, `KNO→CGK` offer, 2 ADT + 1 CHD)**
```json
{
  "passengers": [
    { "firstName": "BUDI", "lastName": "SANTOSO", "passengerType": "ADT", "sex": "M", "birthDay": "1990-01-15", "nationality": "ID" },
    { "firstName": "SITI", "lastName": "SANTOSO", "passengerType": "ADT", "sex": "F", "birthDay": "1992-03-20", "nationality": "ID" },
    { "firstName": "AGUS", "lastName": "SANTOSO", "passengerType": "CHD", "sex": "M", "birthDay": "2018-07-01", "nationality": "ID" }
  ]
}
```

**Response** — `addedAncillary` has one entry per passenger index that bought an ancillary, and OrderDetail's
`passengerList` returns all 3 passenger objects unchanged. `pnrs[].passengers` also lists all 3 as
`"SANTOSO/BUDI"`, `"SANTOSO/SITI"`, `"SANTOSO/AGUS"`. `total` sums FARE+TAX across all 3 (child fare = 75%
of adult per §4) plus any ancillaries.

---

## 6. `POST /flight/pay/v3`

**Request**
```json
{ "orderId": "4820137655", "payType": "BPA", "accountNumber": "" }
```

**Success response** — order transitions `UNPAID → ISSUED`; a 13-digit ticket is minted per passenger.
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "transactionId": "TXN9182734650",
    "amount": "144.50",
    "currency": "USD",
    "accountNumber": ""
  }
}
```
Errors: `745` orderId empty, `148` order does not exist, `748` duplicate payment.

---

## 7. `POST /flight/orderDetail/v3`

**Request**
```json
{ "orderId": "4820137655" }
```

**Success response** (after Pay → `status: "ISSUED"`, `pnr` + `ticketNumber` populated; passengers echoed verbatim, req #7)
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "orderInfo": {
      "orderId": "4820137655",
      "product": ["BASIC"],
      "issuanceTimeInMins": 120,
      "serviceFeePerPax": null,
      "status": "ISSUED",
      "createdTime": "2026-07-04 09:15:00",
      "updateTime": "2026-07-04 09:16:10",
      "expiredTime": "2026-07-04 09:45:00",
      "payTime": "2026-07-04 09:16:10",
      "amount": "144.50",
      "currency": "USD",
      "accountNumber": ""
    },
    "pnrs": [
      {
        "pnr": "X7GH2K",
        "providerPnr": "",
        "email": "agent@example.com",
        "segments": [ { "depAirport": "CGK", "arrAirport": "DPS", "flightNumber": "GA200" } ],
        "passengers": [
          { "passenger": "MURING BALA/CANDY FREDRICK", "ticketNumber": "1234567890123", "cardNumber": null }
        ]
      }
    ],
    "ancillaryList": [
      { "ancillaryType": "CHECKEDBAGGAGE", "ancillaryCode": 25, "ancillaryPiece": 1, "unitOfMeasurement": "WEIGHT",
        "desc": "25kg", "passengerName": "MURING BALA/CANDY FREDRICK", "cardNumber": "",
        "segments": [ { "depAirport": "CGK", "arrAirport": "DPS", "flightNumber": "GA200" } ] }
    ],
    "penalties": [],
    "ancillaries": [ { "ancillaryType": "FREECHECKEDBAGGAGE", "ancillaryCode": 20, "ancillaryPiece": 1, "unitOfMeasurement": "WEIGHT", "desc": "20kg" } ],
    "flightRefs": [ { "flightIndex": 0, "fareType": "PUBLISH", "brandedFare": "" } ],
    "flights": [ "... same single-flight array as Order ..." ],
    "passengerList": [
      { "firstName": "CANDY FREDRICK", "lastName": "MURING BALA", "passengerType": "ADT",
        "sex": "M", "birthDay": "1997-06-02", "nationality": "MY" }
    ],
    "contactList": [
      { "contactType": "AG", "firstName": "CANDY FREDRICK", "lastName": "MURING BALA",
        "email": "agent@example.com", "phone": "+62-8110000000" }
    ],
    "segments": [
      { "marketingCarrier": "GA", "flightNumber": "GA200", "operatingCarrier": "GA", "operatingFlightNumber": "GA200",
        "depAirport": "CGK", "arrAirport": "DPS", "depTerminal": "", "arrTerminal": "",
        "depTime": "2026-07-10 12:00:00", "arrTime": "2026-07-10 14:00:00", "codeShare": false,
        "aircraftCode": "B738", "fareBasis": "", "brandedFare": "", "duration": 120, "stopovers": [] }
    ]
  }
}
Note: top-level `segments` are full objects (as in Search); the nested `pnrs[].segments` and
`ancillaryList[].segments` stay light (`depAirport`/`arrAirport`/`flightNumber`). `pnrs[].providerPnr`
and top-level `flightRefs` (`flightIndex`/`fareType`/`brandedFare`) match the live supplier capture.
```
Before Pay, `status: "UNPAID"`, `payTime: ""`, and `ticketNumber: ""` (PNR still generated at order time).
Errors: `745` orderId empty, `148` order does not exist.
```
```
Note: `passenger` string format is `LASTNAME/FIRSTNAME`; the request passenger objects are echoed
verbatim under `passengerList` / `contactList` per requirement #7.
```
