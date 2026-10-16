"""Generate the RSA key pair Snowflake uses instead of a password.

Writes ~/.snowflake/rsa_key.p8 (private, never share or commit) and
~/.snowflake/rsa_key.pub (public, pasted into snowflake_setup.sql).
Unencrypted private key keeps this simple for a personal trial; for a client
you'd encrypt it with a passphrase.

    python warehouse/make_keypair.py
"""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

out = Path.home() / ".snowflake"
out.mkdir(exist_ok=True)
priv_path, pub_path = out / "rsa_key.p8", out / "rsa_key.pub"
if priv_path.exists():
    raise SystemExit(f"{priv_path} already exists -- delete it first to regenerate")

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
priv_path.write_bytes(
    key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
)
pub_pem = key.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()
pub_path.write_text(pub_pem)

one_line = "".join(l for l in pub_pem.splitlines() if "-----" not in l)
print(f"Private key: {priv_path}\nPublic key:  {pub_path}\n")
print("Paste this into snowflake_setup.sql as RSA_PUBLIC_KEY:\n")
print(one_line)
