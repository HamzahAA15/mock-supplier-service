"""Unit tests for the mocked payment-gateway service (PAY API adjustment)."""
from app import config
from app.services import payments


def test_normalize_pay_type_defaults_to_bpa():
    assert payments.normalize_pay_type(None) == "BPA"
    assert payments.normalize_pay_type("") == "BPA"
    assert payments.normalize_pay_type("yeepay") == "YEEPAY"


def test_is_wallet():
    assert payments.is_wallet("ANTOM")
    assert payments.is_wallet("yeepay")
    assert not payments.is_wallet("BPA")
    assert not payments.is_wallet(None)


def test_settlement_account_wallet_returns_receiver():
    assert payments.settlement_account("ANTOM", "") == config.WALLET_RECEIVER_ACCOUNTS["ANTOM"]
    # Payer account is ignored on wallet-to-wallet.
    assert payments.settlement_account("YEEPAY", "PAYER_1") == config.WALLET_RECEIVER_ACCOUNTS["YEEPAY"]


def test_settlement_account_bpa_echoes_payer():
    assert payments.settlement_account("BPA", "TVLK_ACC") == "TVLK_ACC"
    assert payments.settlement_account("BPA", None) == ""


def test_charge_response_shape():
    order = {"total": 107.0}
    receipt = payments.charge(order, "ANTOM", "")
    assert set(receipt) == {"transactionId", "amount", "currency", "accountNumber"}
    assert receipt["transactionId"].startswith("TXN")
    assert receipt["amount"] == "107.00"
    assert receipt["currency"] == config.CURRENCY
    assert receipt["accountNumber"] == config.WALLET_RECEIVER_ACCOUNTS["ANTOM"]
