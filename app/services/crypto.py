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


def _normalize_b64(s: str) -> str:
    """Repair base64 that got mangled in transit before decoding.

    The most common corruption for base64 carried in an HTTP body is
    `+` -> ` ` (space), which happens when the body is treated as
    application/x-www-form-urlencoded. We also tolerate base64url (`-`/`_`),
    stray whitespace / MIME chunk newlines, and missing padding.
    """
    s = s.strip()
    s = s.replace(" ", "+")                       # undo form-encoding '+' -> space
    s = "".join(s.split())                        # drop remaining whitespace / newlines
    s = s.replace("-", "+").replace("_", "/")     # accept base64url as well
    s += "=" * (-len(s) % 4)                      # restore padding
    return s


def decrypt_aes_cbc(b64_ciphertext: str) -> str:
    """Reverse the client's encryption: base64 -> AES-CBC decrypt -> unpad -> UTF-8.

    Normalizes common in-transit base64 corruption first (see _normalize_b64).
    Raises on genuinely malformed input (wrong block size, bad padding).
    """
    ct = base64.b64decode(_normalize_b64(b64_ciphertext))
    decryptor = Cipher(algorithms.AES(_KEY), modes.CBC(_IV)).decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    unpadder = padding.PKCS7(_BLOCK_BITS).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")
