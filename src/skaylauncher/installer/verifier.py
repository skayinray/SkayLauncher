"""Optional checksum and Ed25519 verification for downloaded release assets."""

from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PUBLIC_KEYS: dict[str, str] = {
    "hackmeskay": "PgMGi9d7BTVYQy3G5UsL+yNn9ldbkrj1RBrThDA46Fc=",
    "skaycleartux": "5KD4tzB9obPd8wPN6soWC10dsnoMqX6ln4Pyh5i38ng=",
    "chess.skay": "CtH8fQqA3o/mFsZ2fRRrUzmijmvKL6OMCaDqY4tt37c=",
    "steamsnm": "L8sewAYfEw4vpC64CR0CPOBQ4YcLgSx3t/LkwL4l7I0=",
    "skaylauncher": "WxuPjONAgTl81lw5mZT0hOwXFS2epOZb7G/aswOGVXk=",
}


class VerificationError(Exception):
    pass


@dataclass
class VerificationResult:
    sha256: str
    checksum_verified: bool
    signature_verified: bool
    note: str = ""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_sha256_sums(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        checksum, name = parts
        if len(checksum) != 64:
            continue
        try:
            int(checksum, 16)
        except ValueError:
            continue
        result[Path(name.strip().lstrip("*")).name] = checksum.lower()
    return result


def _public_key(repo: str, public_key_b64: str | None) -> Ed25519PublicKey | None:
    raw = public_key_b64 or PUBLIC_KEYS.get(repo.lower())
    if not raw:
        return None
    try:
        key_bytes = base64.b64decode("".join(raw.split()), validate=True)
        return Ed25519PublicKey.from_public_bytes(key_bytes)
    except (binascii.Error, ValueError, TypeError) as error:
        raise VerificationError(f"Invalid Ed25519 public key: {error}") from error


def _decode_signature(path: Path) -> bytes:
    try:
        return base64.b64decode("".join(path.read_text(encoding="ascii").split()), validate=True)
    except (OSError, UnicodeError, binascii.Error) as error:
        raise VerificationError(f"Invalid signature file {path.name}: {error}") from error


class ReleaseVerifier:
    def __init__(self, public_key_b64: str | None = None) -> None:
        self.public_key_b64 = public_key_b64

    def verify_asset(
        self,
        path: str | Path,
        companion_dir: str | Path,
        repo: str = "",
        asset_name: str = "",
    ) -> VerificationResult:
        target = Path(path)
        folder = Path(companion_dir)
        digest = sha256_file(target)
        name = asset_name or target.name
        checksum_verified = False
        note = ""

        sums_path = folder / "SHA256SUMS"
        if sums_path.is_file():
            sums = parse_sha256_sums(sums_path.read_text(encoding="utf-8", errors="replace"))
            expected = sums.get(Path(name).name) or sums.get(target.name)
            if expected is None:
                note = f"{name} is not listed in SHA256SUMS"
            elif expected != digest:
                raise VerificationError(f"SHA-256 mismatch for {name}")
            else:
                checksum_verified = True

        signature_verified = False
        sig_path = folder / f"{target.name}.sig"
        if not sig_path.is_file():
            sig_path = folder / f"{Path(name).name}.sig"
        key = _public_key(repo, self.public_key_b64)

        if sig_path.is_file() and key is not None:
            signature = _decode_signature(sig_path)
            payload = target.read_bytes()
            try:
                key.verify(signature, payload)
                signature_verified = True
            except InvalidSignature:
                try:
                    key.verify(signature, bytes.fromhex(digest))
                    signature_verified = True
                except InvalidSignature as error:
                    raise VerificationError(f"Ed25519 signature mismatch for {name}") from error
        elif sig_path.is_file():
            note = f"signature present but no public key is configured for {repo or 'this app'}"

        checksums_sig = folder / "SHA256SUMS.sig"
        if not signature_verified and checksums_sig.is_file() and key is not None and sums_path.is_file():
            signature = _decode_signature(checksums_sig)
            try:
                key.verify(signature, sums_path.read_bytes())
                signature_verified = True
                if not checksum_verified and sums_path.is_file():
                    checksum_verified = True
            except InvalidSignature as error:
                raise VerificationError("SHA256SUMS signature mismatch") from error

        return VerificationResult(
            sha256=digest,
            checksum_verified=checksum_verified,
            signature_verified=signature_verified,
            note=note,
        )
