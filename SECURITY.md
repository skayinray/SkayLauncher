# Security and release verification

SkayLauncher uses HTTPS for GitHub API requests and asset downloads. TLS verification stays enabled, including in the AppImage, which ships a CA bundle that `AppRun` exports as `SSL_CERT_FILE`.

## Ed25519 public key

Release assets are signed with a project Ed25519 key. The raw public key, base64 encoded, is:

```text
WxuPjONAgTl81lw5mZT0hOwXFS2epOZb7G/aswOGVXk=
```

The key is embedded in `tools/sign_release.py` and in `skaylauncher.installer.verifier`. Verification does not require the private key.

## Verify assets

Each release contains `SHA256SUMS` and one `<asset>.sig` file per asset. A `.sig` file is base64 text containing an Ed25519 signature over the raw bytes of the corresponding file. `SHA256SUMS.sig` covers the raw bytes of `SHA256SUMS`.

Linux:

```sh
python -m pip install -r requirements-dev.txt
python tools/sign_release.py verify SkayLauncher-x86_64.AppImage SkayLauncher-x86_64.AppImage.sig
sha256sum -c SHA256SUMS
```

Windows:

```bat
python -m pip install -r requirements-dev.txt
python tools\sign_release.py verify SkayLauncher.exe SkayLauncher.exe.sig
certutil -hashfile SkayLauncher.exe SHA256
```

Compare the `certutil` output with the `SkayLauncher.exe` line in `SHA256SUMS`. Stop if a signature or checksum does not match.

The release workflow also signs the combined `SHA256SUMS` file and verifies every signature before publishing. A missing signing key fails tag builds.

## Signing key handling

The private key is stored only in the GitHub repository secret `RELEASE_SIGNING_KEY`. It is a base64 encoded PKCS8 PEM Ed25519 private key. It is never committed and is not available to verifiers.

For local signing tests, generate a throwaway key and pass it through the environment. Never write a private key into the repository.

## Platform scope

The Ed25519 signatures prove that an asset was produced by the release workflow. They are not operating system code signing.

- The Windows asset is a portable EXE without Authenticode. A paid code signing certificate would be needed for that.
- There is no signed or notarized macOS build. A paid Apple Developer certificate would be needed for that.
- macOS packaging is a manual path and is not part of CI.

## Reporting issues

Use a private GitHub security advisory for security reports. Do not open a public issue for a vulnerability and do not include tokens, private keys, or other credentials in a report.
