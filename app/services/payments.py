"""Mocked payment-gateway responses for POST /flight/pay/v3.

Implements the "PAY API adjustment" wiki:

* ``BPA``    — existing balance-payment flow; the response ``accountNumber``
  echoes the payer account sent in the request.
* ``ANTOM`` / ``YEEPAY`` — wallet-to-wallet gateways; the request
  ``accountNumber`` is expected empty (ignored if provided) and the mocked
  gateway response carries the RECEIVER account of the wallet-to-wallet
  transaction (fixed per gateway in ``config.WALLET_RECEIVER_ACCOUNTS``).

The response shape is identical for every gateway:
``{transactionId, amount, currency, accountNumber}``.
"""
from app import config
from app.services.orders import new_transaction_id

DEFAULT_PAY_TYPE = "BPA"


def normalize_pay_type(pay_type: str) -> str:
    """Uppercase the payType, defaulting to BPA when absent."""
    return (pay_type or DEFAULT_PAY_TYPE).upper()


def is_wallet(pay_type: str) -> bool:
    """True when the payType is a wallet-to-wallet gateway (ANTOM/YEEPAY)."""
    return normalize_pay_type(pay_type) in config.WALLET_RECEIVER_ACCOUNTS


def settlement_account(pay_type: str, payer_account_number: str) -> str:
    """Account number to expose on the payment response and the order.

    Wallet gateways return the receiver account; every other gateway echoes
    the payer's account number from the request.
    """
    normalized = normalize_pay_type(pay_type)
    if normalized in config.WALLET_RECEIVER_ACCOUNTS:
        return config.WALLET_RECEIVER_ACCOUNTS[normalized]
    return payer_account_number or ""


def charge(order: dict, pay_type: str, payer_account_number: str) -> dict:
    """Return the mocked gateway response for a successful payment."""
    return {
        "transactionId": new_transaction_id(),
        "amount": "{:.2f}".format(order["total"]),
        "currency": config.CURRENCY,
        "accountNumber": settlement_account(pay_type, payer_account_number),
    }
