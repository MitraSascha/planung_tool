"""Erzeugt ein VAPID-Schluesselpaar fuer Web-Push.

Einmalig pro Deployment ausfuehren. Die Ausgabe ist ein ``.env``-Snippet,
das direkt in die Backend-Konfiguration kopiert werden kann::

    .venv/bin/python -m scripts.generate_vapid_keys >> .env

Hinweis: Auf gemeinsamen Schluesseln basieren saemtliche bestehenden
Browser-Subscriptions. Wer den Private-Key rotiert, ungueltigsiert
saemtliche frueheren Push-Subscriptions — die Clients muessen sich neu
abonnieren.
"""
from __future__ import annotations

import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_vapid_keypair() -> tuple[str, str]:
    """Erzeugt ein P-256 ECDSA Schluesselpaar und liefert (public_b64url, private_b64url).

    Das Format ist kompatibel mit ``py_vapid`` / ``pywebpush``:
    - Public Key:  65 Byte uncompressed point (0x04 || X || Y), base64url ohne Padding.
    - Private Key: 32 Byte Secret-Scalar, base64url ohne Padding.
    """
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_numbers = private_key.public_key().public_numbers()

    # Uncompressed point: 0x04 || X (32B) || Y (32B)
    x_bytes = public_numbers.x.to_bytes(32, "big")
    y_bytes = public_numbers.y.to_bytes(32, "big")
    public_bytes = b"\x04" + x_bytes + y_bytes

    private_bytes = private_key.private_numbers().private_value.to_bytes(32, "big")

    return _b64url(public_bytes), _b64url(private_bytes)


def main() -> None:
    public_key, private_key = generate_vapid_keypair()

    print("# === VAPID Schluesselpaar fuer Web-Push (Phase 14.4) ===")
    print("# Einmalig generiert. Privaten Schluessel niemals committen.")
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print("VAPID_SUBJECT=mailto:admin@hez.tech-artist.de")


if __name__ == "__main__":  # pragma: no cover
    main()
