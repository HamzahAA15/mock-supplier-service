"""AES-CBC helper for the Second Baggage order endpoint.

The client encrypts the /orderCrossSecondBaggage request body with
AES/CBC/PKCS5Padding and base64-encodes the result (Java: SecretKeySpec + IV,
Base64.encodeBase64). PKCS5 == PKCS7 for AES's 16-byte block.

Per the agreed integration contract:
- key = the 16-byte shared key below (AES-128)
- IV  = the key bytes (Java `IvParameterSpec(key.getBytes())`)
- base64 = standard alphabet

The key is a shared symmetric integration key for the mock; override via the
SECOND_BAGGAGE_AES_KEY env var if needed.
"""
import base64
import os

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_KEY = os.environ.get("SECOND_BAGGAGE_AES_KEY", "B@4p6aay&)*^M0^r").encode("utf-8")
_IV = _KEY  # IvParameterSpec(key.getBytes()) — key reused as IV
_BLOCK_BITS = 128


def encrypt_aes_cbc(plaintext: str) -> str:
    """Mirror of the client's Java encryption (for tests/parity)."""
    padder = padding.PKCS7(_BLOCK_BITS).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(_KEY), modes.CBC(_IV)).encryptor()
    ct = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ct).decode("ascii")


def decrypt_aes_cbc(b64_ciphertext: str) -> str:
    """Reverse the client's encryption: base64 -> AES-CBC decrypt -> unpad -> UTF-8.

    Raises on any malformed input (bad base64, wrong block size, bad padding).
    """
    ct = base64.b64decode(b64_ciphertext, validate=True)
    decryptor = Cipher(algorithms.AES(_KEY), modes.CBC(_IV)).decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    unpadder = padding.PKCS7(_BLOCK_BITS).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")
