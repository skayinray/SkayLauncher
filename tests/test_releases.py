from skaylauncher.api.releases import parse_release, parse_repositories, release_summary
from skaylauncher.core.models import PlatformInfo
from skaylauncher.core.platform import choose_asset


def payload_repo(name, **extra):
    data = {
        "id": 1,
        "name": name,
        "full_name": f"skayinray/{name}",
        "html_url": f"https://github.com/skayinray/{name}",
        "description": "A tool",
        "topics": ["python", "qt"],
        "pushed_at": "2026-11-21T10:00:00Z",
        "fork": False,
        "archived": False,
    }
    data.update(extra)
    return data


def payload_release(tag="v1.2.3", assets=None):
    return {
        "tag_name": tag,
        "name": tag,
        "body": "Fixed bugs.",
        "published_at": "2026-11-20T10:00:00Z",
        "html_url": "https://github.com/skayinray/app/releases/tag/v1.2.3",
        "assets": assets or [],
    }


def test_parse_release_maps_assets():
    release = parse_release(payload_release(assets=[{
        "name": "app-x86_64.AppImage",
        "browser_download_url": "https://example.invalid/app.AppImage",
        "size": 123,
        "content_type": "application/octet-stream",
    }]))
    assert release is not None
    assert release.version == "1.2.3"
    assert release.assets[0].size == 123
    assert release_summary(release).startswith("v1.2.3")


def test_parse_repositories_filters_launcher_forks_and_archived():
    repos = parse_repositories(
        [
            payload_repo("chess.skay"),
            payload_repo("SkayLauncher"),
            payload_repo("forked", fork=True),
            payload_repo("old", archived=True),
        ],
        {"chess.skay": payload_release()},
    )
    assert [repo.name for repo in repos] == ["chess.skay"]
    assert repos[0].topics == ("python", "qt")
    assert repos[0].latest_version == "1.2.3"


def test_parse_repositories_can_include_forks():
    repos = parse_repositories([payload_repo("forked", fork=True)], {}, include_forks=True)
    assert [repo.name for repo in repos] == ["forked"]


def test_latest_asset_selection_from_parsed_release():
    release = parse_release(payload_release(assets=[
        {"name": "app-aarch64.AppImage", "browser_download_url": "https://example.invalid/a"},
        {"name": "app-x86_64.AppImage", "browser_download_url": "https://example.invalid/b"},
    ]))
    info = PlatformInfo(system="linux", machine="x86_64")
    chosen = choose_asset(release, info)
    assert chosen is not None and chosen.name == "app-x86_64.AppImage"
