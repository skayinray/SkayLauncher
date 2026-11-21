"""Atomic filesystem helpers used by installs, settings and self-update."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


def atomic_write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    atomic_replace(temp, target)


def atomic_write_json(path: str | Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def atomic_replace(source: str | Path, destination: str | Path) -> None:
    src = Path(source)
    dst = Path(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_dir() and not src.is_dir():
        shutil.rmtree(dst)
    if src.is_dir():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(src), str(dst))
        return
    if dst.exists():
        backup = dst.with_name(f".{dst.name}.old")
        if backup.exists():
            backup.unlink()
        os.replace(dst, backup)
    os.replace(src, dst)
    try:
        backup = dst.with_name(f".{dst.name}.old")
        if backup.exists():
            backup.unlink()
    except OSError:
        pass


def remove_path(path: str | Path) -> None:
    target = Path(path)
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    elif target.exists() or target.is_symlink():
        try:
            target.unlink()
        except OSError:
            pass
