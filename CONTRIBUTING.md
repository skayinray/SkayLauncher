# Contributing

## Development setup

Python 3.11 or newer is required.

```sh
python -m pip install -e ".[dev,build]"
python SkayLauncher.py
```

Install from `requirements.txt` and `requirements-dev.txt` if you do not want an editable install:

```sh
python -m pip install -r requirements.txt -r requirements-dev.txt
```

## Checks

Run these before opening a pull request:

```sh
ruff check .
python -m compileall -q src tools SkayLauncher.py
python -m pytest -q
```

CI runs the same checks on Ubuntu and Windows with Python 3.11 and 3.12. Tests must not require network access or a display.

## Code style

- Keep repository documentation in clear English.
- Prefer small functions and explicit types.
- Keep platform specific behavior in focused modules.
- Do not disable TLS verification or weaken release verification.
- Do not add unused PySide6 modules to the packaged builds.

## Releases

Releases are built from `v*` tags by `.github/workflows/build.yml`. The workflow builds the Linux AppImage and Windows EXE, signs every asset with `RELEASE_SIGNING_KEY`, verifies the signatures, and uploads the release files.

The private signing key must stay in the GitHub secret store. Do not copy it into source files, logs, issues, or test fixtures. For local signing tests, generate a throwaway key and pass it through `RELEASE_SIGNING_KEY`.

## Scope

Keep changes focused. Include tests for behavior changes in API, storage, installer, or updater code. Update `README.md` or `SECURITY.md` when user instructions or the verification flow change.
