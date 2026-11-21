"""Self-update logic for the packaged launcher."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..api.github import GitHubClient
from ..api.releases import parse_release
from ..core.atomic import atomic_replace
from ..core.models import PlatformInfo, Release, ReleaseAsset, compare_versions
from ..core.paths import PathManager
from ..core.platform import choose_asset, current_platform
from ..installer.verifier import ReleaseVerifier, VerificationError, VerificationResult

ProgressCallback = Callable[[int, int], None]
TEMPLATE = Path(__file__).with_name("windows_replace.ps1")


class UpdateNotApplicable(Exception):
    pass


@dataclass
class UpdateCheck:
    available: bool
    version: str
    release: Release | None
    asset: ReleaseAsset | None

    @classmethod
    def empty(cls) -> UpdateCheck:
        return cls(available=False, version="", release=None, asset=None)


@dataclass
class PreparedUpdate:
    path: Path
    verification: VerificationResult


class SelfUpdater:
    def __init__(
        self,
        client: GitHubClient,
        paths: PathManager,
        current_version: str,
        platform_info: PlatformInfo | None = None,
        verifier: ReleaseVerifier | None = None,
        frozen: bool | None = None,
    ) -> None:
        self.client = client
        self.paths = paths
        self.current_version = current_version
        self.platform = platform_info or current_platform()
        self.verifier = verifier or ReleaseVerifier()
        self.frozen = getattr(sys, "frozen", False) if frozen is None else frozen

    def current_executable(self) -> Path:
        appimage = os.environ.get("APPIMAGE")
        if appimage and Path(appimage).exists():
            return Path(appimage)
        if getattr(sys, "frozen", False):
            return Path(sys.executable)
        return Path(sys.argv[0]).resolve()

    def check(self) -> UpdateCheck:
        payload = self.client.get_latest_release("SkayLauncher")
        release = parse_release(payload)
        if release is None:
            return UpdateCheck.empty()
        asset = choose_asset(release, self.platform)
        available = compare_versions(release.version, self.current_version) > 0 and asset is not None
        return UpdateCheck(
            available=available,
            version=release.version,
            release=release,
            asset=asset if available else None,
        )

    def prepare(self, check: UpdateCheck, progress: ProgressCallback | None = None) -> PreparedUpdate:
        if not check.available or check.release is None or check.asset is None:
            raise UpdateNotApplicable("No launcher update is available")
        folder = self.paths.downloads_dir / f"selfupdate-{uuid.uuid4().hex}"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / check.asset.name
        self.client.download_asset(check.asset.url, target, progress)
        for companion in check.release.assets:
            if companion.name == check.asset.name or not self._is_companion(companion.name):
                continue
            self.client.download_asset(companion.url, folder / companion.name)
        try:
            verification = self.verifier.verify_asset(target, folder, repo="SkayLauncher")
        except VerificationError:
            raise
        except Exception as error:  # noqa: BLE001
            raise VerificationError(f"Launcher update verification failed: {error}") from error
        return PreparedUpdate(path=target, verification=verification)

    @staticmethod
    def _is_companion(name: str) -> bool:
        lowered = name.lower()
        return lowered in {"sha256sums", "shasums"} or lowered.endswith((".sig", ".sha256", ".txt"))

    def apply(self, prepared: PreparedUpdate) -> str:
        if not self.frozen:
            raise UpdateNotApplicable("Self-update is only available in packaged builds")
        current = self.current_executable()
        if not current.is_file():
            raise UpdateNotApplicable(f"Cannot locate current executable: {current}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = self.paths.backups_dir / f"{current.name}.{stamp}.bak"
        shutil.copy2(current, backup)
        if self.platform.is_linux:
            if current.suffix.lower() != ".appimage" and ".AppImage" not in current.name:
                raise UpdateNotApplicable(f"Linux self-update needs an AppImage path: {current}")
            mode = prepared.path.stat().st_mode
            prepared.path.chmod(mode | 0o111)
            atomic_replace(prepared.path, current)
            return "applied"
        script = self.paths.cache_dir / f"replace-{uuid.uuid4().hex}.ps1"
        script.write_text(
            TEMPLATE.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        args = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(prepared.path),
            "-Target",
            str(current),
            "-Backup",
            str(backup),
            "-LauncherPid",
            str(os.getpid()),
        ]
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            close_fds=True,
        )
        return "pending_restart"
