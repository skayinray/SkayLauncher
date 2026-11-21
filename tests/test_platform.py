from skaylauncher.core.models import PlatformInfo, Release, ReleaseAsset
from skaylauncher.core.platform import choose_asset, score_asset


def release_with(*names):
    return Release(
        tag="v1",
        name="v1",
        body="",
        published_at="",
        assets=tuple(ReleaseAsset(name=name, url=f"https://example.invalid/{name}") for name in names),
    )


def test_choose_linux_appimage():
    info = PlatformInfo(system="linux", machine="x86_64")
    release = release_with("app.AppImage.sig", "app-arm64.AppImage", "app-x86_64.AppImage", "source.zip")
    chosen = choose_asset(release, info)
    assert chosen is not None
    assert chosen.name == "app-x86_64.AppImage"


def test_choose_windows_exe_or_zip():
    info = PlatformInfo(system="windows", machine="x86_64")
    release = release_with("SHA256SUMS", "app-windows.zip", "app-x86_64.exe")
    chosen = choose_asset(release, info)
    assert chosen is not None
    assert chosen.name == "app-x86_64.exe"


def test_unsupported_architecture_is_not_selected():
    info = PlatformInfo(system="linux", machine="x86_64")
    release = release_with("app-aarch64.AppImage")
    assert choose_asset(release, info) is None
    assert all(score_asset(asset, info) <= 0 for asset in release.assets)
