import base64
import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from skaylauncher.installer.verifier import (
    VerificationError,
    parse_sha256_sums,
    sha256_file,
)


@pytest.fixture
def signing_key():
    return ed25519.Ed25519PrivateKey.generate()


def public_b64(key):
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def write_sums(folder, name, digest):
    (folder / "SHA256SUMS").write_text(f"{digest}  {name}\n", encoding="ascii")


def test_parse_sha256_sums():
    text = "# comment\n abc  app.AppImage\n" + "0" * 64 + "  app.zip\n"
    result = parse_sha256_sums(text)
    assert result["app.zip"] == "0" * 64
    assert "abc" not in result


def test_checksum_and_raw_signature_verify(tmp_path, signing_key):
    from skaylauncher.installer.verifier import ReleaseVerifier

    asset = tmp_path / "app.AppImage"
    asset.write_bytes(b"release bytes")
    digest = sha256_file(asset)
    write_sums(tmp_path, "app.AppImage", digest)
    sig = signing_key.sign(asset.read_bytes())
    (tmp_path / "app.AppImage.sig").write_text(base64.b64encode(sig).decode() + "\n")

    verifier = ReleaseVerifier(public_b64(signing_key))
    result = verifier.verify_asset(asset, tmp_path, repo="test")
    assert result.checksum_verified is True
    assert result.signature_verified is True
    assert result.sha256 == digest


def test_digest_signature_is_accepted(tmp_path, signing_key):
    from skaylauncher.installer.verifier import ReleaseVerifier

    asset = tmp_path / "app.exe"
    asset.write_bytes(b"payload")
    digest = sha256_file(asset)
    sig = signing_key.sign(bytes.fromhex(digest))
    (tmp_path / "app.exe.sig").write_text(base64.b64encode(sig).decode())

    verifier = ReleaseVerifier(public_b64(signing_key))
    result = verifier.verify_asset(asset, tmp_path)
    assert result.signature_verified is True


def test_checksum_mismatch_is_rejected(tmp_path, signing_key):
    from skaylauncher.installer.verifier import ReleaseVerifier

    asset = tmp_path / "app.AppImage"
    asset.write_bytes(b"payload")
    write_sums(tmp_path, "app.AppImage", "0" * 64)
    with pytest.raises(VerificationError, match="SHA-256 mismatch"):
        ReleaseVerifier(public_b64(signing_key)).verify_asset(asset, tmp_path)


def test_bad_signature_is_rejected(tmp_path, signing_key):
    from skaylauncher.installer.verifier import ReleaseVerifier

    asset = tmp_path / "app.AppImage"
    asset.write_bytes(b"payload")
    other = ed25519.Ed25519PrivateKey.generate()
    sig = other.sign(b"payload")
    (tmp_path / "app.AppImage.sig").write_text(base64.b64encode(sig).decode())
    with pytest.raises(VerificationError, match="signature mismatch"):
        ReleaseVerifier(public_b64(signing_key)).verify_asset(asset, tmp_path)


def test_unknown_key_does_not_fail_but_reports_note(tmp_path):
    from skaylauncher.installer.verifier import ReleaseVerifier

    asset = tmp_path / "unknown.bin"
    asset.write_bytes(b"data")
    sig = ed25519.Ed25519PrivateKey.generate().sign(b"data")
    (tmp_path / "unknown.bin.sig").write_text(base64.b64encode(sig).decode())
    result = ReleaseVerifier().verify_asset(asset, tmp_path, repo="unknown")
    assert result.signature_verified is False
    assert "no public key" in result.note


def test_sha256_file_is_stable(tmp_path):
    asset = tmp_path / "file"
    asset.write_bytes(b"abc")
    assert sha256_file(asset) == hashlib.sha256(b"abc").hexdigest()
