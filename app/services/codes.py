"""Business result codes and envelope helpers (DESIGN.md section 8)."""

SUCCESS = 0
OFFER_KEY_EMPTY = 101
ORDER_NOT_FOUND = 148
AIRPORT_EMPTY = 201
DEP_DATE_EMPTY = 203
NO_DATA = 204
DEP_DATE_BACKDATE = 205
ROUTE_EMPTY = 206
NO_ADULT = 241
EMAIL_EMPTY = 529
EMAIL_BAD_FORMAT = 530
PHONE_EMPTY = 531
ANCILLARY_EXPIRED = 553
ORDER_ID_EMPTY = 745
DUPLICATE_PAYMENT = 748

MESSAGES = {
    SUCCESS: "success",
    OFFER_KEY_EMPTY: "The offerKey cannot be empty",
    ORDER_NOT_FOUND: "The order does not exist",
    AIRPORT_EMPTY: "The departure or arrival airport cannot be empty",
    DEP_DATE_EMPTY: "The departure date cannot be empty",
    NO_DATA: "No data",
    DEP_DATE_BACKDATE: "The departure date cannot be earlier than the current time",
    ROUTE_EMPTY: "The route info cannot be empty",
    NO_ADULT: "At least one adult passenger is required",
    EMAIL_EMPTY: "The contact email cannot be empty",
    EMAIL_BAD_FORMAT: "The contact email format is invalid",
    PHONE_EMPTY: "The contact phone cannot be empty",
    ANCILLARY_EXPIRED: "The ancillary offer has expired",
    ORDER_ID_EMPTY: "The orderId cannot be empty",
    DUPLICATE_PAYMENT: "Duplicate payment",
}


def envelope(code, data=None, msg=None):
    return {"code": code, "msg": msg or MESSAGES.get(code, ""), "data": data}


def success(data):
    return envelope(SUCCESS, data)


def error(code, msg=None):
    return envelope(code, None, msg)
