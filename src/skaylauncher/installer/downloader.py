"""Downloads release assets and verifies them before installation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..api.github import GitHubClient
from ..core.models import Release, ReleaseAsset
from ..core.paths import PathManager
from .verifier import ReleaseVerifier, VerificationError, VerificationResult

ProgressCallback = Callable[[int, int], None]


@dataclass
class DownloadResult:
    path: Path
    asset: ReleaseAsset
    release: Release
    verification: VerificationResult


class DownloadManager:
    def __init__(self, client: GitHubClient, paths: PathManager, verifier: ReleaseVerifier | None = None) -> None:
        self.client = client
        self.paths = paths
        self.verifier = verifier or ReleaseVerifier()

    def download(
        self,
        repo: str,
        release: Release,
        asset: ReleaseAsset,
        progress: ProgressCallback | None = None,
        extra_assets: list[ReleaseAsset] | None = None,
    ) -> DownloadResult:
        folder = self.paths.downloads_dir / f"{uuid.uuid4().hex}"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / asset.name
        self.client.download_asset(asset.url, target, progress)
        for companion in extra_assets or []:
            if companion.name in {asset.name, "SHA256SUMS"}:
                continue
            if companion.name.endswith((".sig", ".sha256", ".txt")) or companion.name == "SHA256SUMS":
                self.client.download_asset(companion.url, folder / companion.name)
        try:
            verification = self.verifier.verify_asset(target, folder, repo=repo, asset_name=asset.name)
        except VerificationError:
            raise
        except Exception as error:  # noqa: BLE001
            raise VerificationError(f"Verification failed: {error}") from error
        return DownloadResult(path=target, asset=asset, release=release, verification=verification)
