"""Sign release assets and verify them with an embedded Ed25519 public key.

Commands:
    python tools/sign_release.py sign FILE [FILE ...]
    python tools/sign_release.py sign-only FILE
    python tools/sign_release.py verify FILE FILE.sig

``sign`` reads a base64 encoded PKCS8 PEM Ed25519 private key from the
``RELEASE_SIGNING_KEY`` environment variable. For each input file it writes
``FILE.sig`` containing a base64 signature over the raw file bytes, and it
writes ``SHA256SUMS`` in the current directory.

``sign-only`` signs one existing file, for example a combined ``SHA256SUMS``,
without rewriting the checksum manifest.

``verify`` uses the embedded public key by default. The optional
``--public-key`` flag exists for local tests with a generated key and must not
be used for release verification.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import os
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

ENV_KEY = "RELEASE_SIGNING_KEY"
PUBLIC_KEY_B64 = "WxuPjONAgTl81lw5mZT0hOwXFS2epOZb7G/aswOGVXk="


class ReleaseSigningError(Exception):
    """Raised for missing keys, bad input files, or failed verification."""


def _decode_b64(text: str, label: str) -> bytes:
    compact = "".join(text.split())
    if not compact:
        raise ReleaseSigningError(f"{label} is empty")
    try:
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ReleaseSigningError(f"{label} is not valid base64: {error}") from error


def _private_key() -> Ed25519PrivateKey:
    encoded = os.environ.get(ENV_KEY, "").strip()
    if not encoded:
        raise ReleaseSigningError(
            f"{ENV_KEY} is not set; export the base64 PKCS8 PEM Ed25519 private key first"
        )
    try:
        key = serialization.load_pem_private_key(_decode_b64(encoded, ENV_KEY), password=None)
    except (TypeError, ValueError) as error:
        raise ReleaseSigningError(f"{ENV_KEY} is not a valid PEM private key: {error}") from error
    if not isinstance(key, Ed25519PrivateKey):
        raise ReleaseSigningError(f"{ENV_KEY} must contain an Ed25519 private key")
    return key


def _public_key(public_key_b64: str | None = None) -> Ed25519PublicKey:
    encoded = PUBLIC_KEY_B64 if public_key_b64 is None else public_key_b64
    try:
        return Ed25519PublicKey.from_public_bytes(_decode_b64(encoded, "public key"))
    except ValueError as error:
        raise ReleaseSigningError(f"invalid Ed25519 public key: {error}") from error


def _read_payload(path: Path) -> bytes:
    if not path.is_file():
        raise ReleaseSigningError(f"file not found: {path}")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ReleaseSigningError(f"cannot read {path}: {error}") from error


def _write_signature(path: Path, signature: bytes) -> Path:
    signature_path = path.with_name(path.name + ".sig")
    try:
        signature_path.write_text(
            base64.b64encode(signature).decode("ascii") + "\n", encoding="ascii"
        )
    except OSError as error:
        raise ReleaseSigningError(f"cannot write {signature_path}: {error}") from error
    return signature_path


def _sign_payload(key: Ed25519PrivateKey, path: Path) -> tuple[bytes, str]:
    payload = _read_payload(path)
    return key.sign(payload), hashlib.sha256(payload).hexdigest()


def sign(files: list[str]) -> int:
    """Sign each file and write a SHA256SUMS manifest in the current directory."""
    key = _private_key()
    paths = [Path(name) for name in files]
    for path in paths:
        if not path.is_file():
            raise ReleaseSigningError(f"file not found: {path}")
    names = [path.name for path in paths]
    if len(set(names)) != len(names):
        raise ReleaseSigningError("SHA256SUMS cannot contain duplicate file names")

    checksums: dict[str, str] = {}
    for path in paths:
        signature, digest = _sign_payload(key, path)
        signature_path = _write_signature(path, signature)
        checksums[path.name] = digest
        print(f"signed {path} -> {signature_path}")

    lines = [f"{checksums[name]}  {name}\n" for name in sorted(checksums)]
    try:
        Path("SHA256SUMS").write_text("".join(lines), encoding="ascii")
    except OSError as error:
        raise ReleaseSigningError(f"cannot write SHA256SUMS: {error}") from error
    print(f"wrote SHA256SUMS ({len(lines)} entries)")
    return 0


def sign_only(name: str) -> int:
    """Sign one existing file without changing a checksum manifest."""
    key = _private_key()
    path = Path(name)
    signature, _digest = _sign_payload(key, path)
    signature_path = _write_signature(path, signature)
    print(f"signed {path} -> {signature_path}")
    return 0


def verify(name: str, signature_name: str, public_key_b64: str | None = None) -> int:
    """Verify raw file bytes against a base64 Ed25519 signature file."""
    path = Path(name)
    signature_path = Path(signature_name)
    payload = _read_payload(path)
    signature_text = _read_payload(signature_path).decode("ascii", errors="strict")
    signature = _decode_b64(signature_text, f"signature file {signature_path}")

    try:
        _public_key(public_key_b64).verify(signature, payload)
    except InvalidSignature as error:
        raise ReleaseSigningError(
            f"invalid signature for {path}: file contents or signature do not match the public key"
        ) from error
    print(f"OK: {path} matches the Ed25519 public key")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sign and verify SkayLauncher release assets")
    commands = parser.add_subparsers(dest="command", required=True)

    sign_parser = commands.add_parser("sign", help="sign files and write SHA256SUMS")
    sign_parser.add_argument("files", nargs="+", help="files to sign")

    only_parser = commands.add_parser("sign-only", help="sign one file without rewriting SHA256SUMS")
    only_parser.add_argument("file", help="file to sign")

    verify_parser = commands.add_parser("verify", help="verify one file against its signature")
    verify_parser.add_argument("file", help="file to verify")
    verify_parser.add_argument("signature", help="base64 .sig file")
    verify_parser.add_argument(
        "--public-key",
        help="override the embedded key for local tests only",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "sign":
            return sign(args.files)
        if args.command == "sign-only":
            return sign_only(args.file)
        return verify(args.file, args.signature, args.public_key)
    except ReleaseSigningError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
