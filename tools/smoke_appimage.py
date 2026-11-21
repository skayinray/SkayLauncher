"""Smoke-test a built AppImage without a display or FUSE.

The process must stay alive for a few seconds with no fatal output. This
catches missing bundled libraries that a successful build alone does not.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

FATAL_MARKERS = (
    "Traceback (most recent call last)",
    "ImportError",
    "error while loading shared libraries",
    "Could not load the Qt platform plugin",
)


def smoke(image: Path, wait: float = 12.0) -> int:
    if not image.is_file():
        raise SystemExit(f"AppImage not found: {image}")
    home = Path(tempfile.mkdtemp(prefix="skaylauncher-smoke-"))
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SKAYLAUNCHER_HOME"] = str(home)
    env["APPIMAGELAUNCHER_DISABLE"] = "1"
    env.pop("DISPLAY", None)

    log = home / "stderr.log"
    with log.open("wb") as errors:
        process = subprocess.Popen(
            [str(image.resolve()), "--appimage-extract-and-run", "--no-self-update"],
            stdout=errors,
            stderr=errors,
            env=env,
            cwd=str(home),
            start_new_session=True,
        )
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.25)
        alive = process.poll() is None
        if alive:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)

    output = log.read_text(encoding="utf-8", errors="replace")
    if any(marker in output for marker in FATAL_MARKERS):
        print(output[-4000:])
        raise SystemExit("AppImage smoke test failed: fatal output on startup")
    if not alive:
        print(output[-4000:])
        raise SystemExit(f"AppImage smoke test failed: exited with status {process.returncode}")
    print(f"AppImage started successfully: {image.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", nargs="?", default="SkayLauncher-x86_64.AppImage", type=Path)
    parser.add_argument("--wait", type=float, default=12.0)
    args = parser.parse_args()
    return smoke(args.image, args.wait)


if __name__ == "__main__":
    raise SystemExit(main())
