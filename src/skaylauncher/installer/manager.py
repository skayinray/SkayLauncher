"""Install, launch and remove applications from local release assets."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..core.apps import InstallRegistry
from ..core.models import InstalledApp, PlatformInfo, Release
from ..core.paths import PathManager
from ..core.platform import choose_asset, current_platform
from .downloader import DownloadManager

ProgressCallback = Callable[[int, int], None]


class InstallationError(Exception):
    pass


class AppInstaller:
    def __init__(
        self,
        paths: PathManager,
        registry: InstallRegistry,
        downloader: DownloadManager,
        platform_info: PlatformInfo | None = None,
    ) -> None:
        self.paths = paths
        self.registry = registry
        self.downloader = downloader
        self.platform = platform_info or current_platform()

    def install(
        self,
        repo: str,
        release: Release,
        asset=None,
        progress: ProgressCallback | None = None,
        extra_assets=None,
    ) -> InstalledApp:
        chosen = asset or choose_asset(release, self.platform)
        if chosen is None:
            raise InstallationError(f"No installable asset for {self.platform.label()}")
        downloaded = self.downloader.download(repo, release, chosen, progress, extra_assets)
        version = release.version or "latest"
        staging = self.paths.app_staging_dir(repo, version)
        target = self.paths.app_install_dir(repo, version)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            executable_rel = self._prepare_staging(downloaded.path, staging)
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            staging.replace(target)
            executable = target / executable_rel
            if self.platform.is_linux:
                self._make_executable(executable)
            record = InstalledApp(
                repo=repo,
                version=version,
                tag=release.tag,
                executable=str(executable),
                directory=str(target),
                asset=chosen.name,
                installed_at=datetime.now(timezone.utc).isoformat(),
            )
            self.registry.upsert(record)
            return record
        except Exception as error:
            shutil.rmtree(staging, ignore_errors=True)
            if isinstance(error, InstallationError):
                raise
            raise InstallationError(f"Install failed for {repo}: {error}") from error

    def _prepare_staging(self, downloaded: Path, staging: Path) -> Path:
        if downloaded.name.lower().endswith(".zip"):
            self._safe_extract(downloaded, staging)
            candidates = self._find_executables(staging)
            if not candidates:
                raise InstallationError(f"No executable found in {downloaded.name}")
            return candidates[0].relative_to(staging)
        destination = staging / downloaded.name
        shutil.copy2(downloaded, destination)
        return Path(downloaded.name)

    def _safe_extract(self, archive: Path, destination: Path) -> None:
        count = 0
        total = 0
        with zipfile.ZipFile(archive) as handle:
            for member in handle.infolist():
                count += 1
                total += member.file_size
                if count > 10_000 or total > 2 * 1024**3:
                    raise InstallationError("Archive is too large or has too many files")
                name = member.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/") or ":" in name:
                    raise InstallationError(f"Unsafe path in archive: {member.filename}")
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                with handle.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

    def _find_executables(self, root: Path) -> list[Path]:
        if self.platform.is_windows:
            candidates = [path for path in root.rglob("*.exe") if path.is_file()]
            candidates.sort(key=lambda path: (len(path.parts), path.name.lower() != "setup.exe"))
            return candidates
        candidates = [path for path in root.rglob("*") if path.is_file() and os.access(path, os.X_OK)]
        candidates.sort(key=lambda path: len(path.parts))
        return candidates

    @staticmethod
    def _make_executable(path: Path) -> None:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def launch(self, repo: str) -> bool:
        record = self.registry.get(repo)
        if record is None:
            return False
        executable = Path(record.executable)
        if not executable.is_file():
            raise InstallationError(f"Executable is missing: {executable}")
        if self.platform.is_linux:
            self._make_executable(executable)
            subprocess.Popen(
                [str(executable)],
                cwd=str(executable.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(
            [str(executable)],
            cwd=str(executable.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        return True

    def uninstall(self, repo: str) -> None:
        record = self.registry.get(repo)
        if record is None:
            return
        directory = Path(record.directory)
        if directory.is_dir():
            shutil.rmtree(directory, ignore_errors=True)
        parent = directory.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
        self.registry.remove(repo)

    def open_folder(self, repo: str) -> bool:
        record = self.registry.get(repo)
        if record is None:
            return False
        folder = Path(record.directory)
        if not folder.is_dir():
            return False
        if self.platform.is_windows:
            subprocess.Popen(["explorer", str(folder)], close_fds=True)
        elif shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(folder)], start_new_session=True)
        return True
