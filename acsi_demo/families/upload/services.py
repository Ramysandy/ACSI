"""Fake storage + scanner for the upload family."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from acsi_demo.harness.checkpoint import checkpoint

FAMILY_META = {
    "handler_name": "handle_upload",
    "description": "Upload a file, scan it, then publish to public/",
}

_world: "UploadWorld | None" = None
_keepalive: list["UploadWorld"] = []


class UploadWorld:
    def __init__(self, root: Path | None = None) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="acsi_upload_")
        self.root = Path(root) if root else Path(self._tmp.name)
        self.public = self.root / "public"
        self.private = self.root / "private"
        self.public.mkdir(parents=True, exist_ok=True)
        self.private.mkdir(parents=True, exist_ok=True)
        self.scan_log: list[str] = []
        self.source_file = self.root / "incoming" / "doc.txt"
        self.source_file.parent.mkdir(parents=True, exist_ok=True)
        self.source_file.write_text("hello-acsi", encoding="utf-8")

    def close(self) -> None:
        self._tmp.cleanup()


def create_world() -> UploadWorld:
    """Create a fresh world. Prior worlds are kept alive until clear_keepalive()."""
    global _world
    _world = UploadWorld()
    _keepalive.append(_world)
    return _world


def clear_keepalive() -> None:
    while _keepalive:
        w = _keepalive.pop()
        try:
            w.close()
        except Exception:
            pass



def get_world() -> UploadWorld:
    if _world is None:
        raise RuntimeError("world not initialized")
    return _world


def snapshot(world: UploadWorld) -> dict[str, Any]:
    def listing(folder: Path) -> list[tuple[str, str]]:
        if not folder.exists():
            return []
        out = []
        for p in sorted(folder.iterdir()):
            if p.is_file():
                out.append((p.name, p.read_text(encoding="utf-8", errors="replace")))
        return out

    return {
        "public": listing(world.public),
        "private": listing(world.private),
        "scan_log": list(world.scan_log),
    }


def build_call_args(world: UploadWorld) -> tuple[tuple, dict]:
    return (str(world.source_file),), {}


def functional_check(result: Any, world: UploadWorld) -> tuple[bool, str]:
    name = Path(world.source_file).name
    pub = world.public / name
    if not pub.exists():
        return False, "published file missing from public/"
    if name not in world.scan_log:
        return False, "file published but not in scan log"
    if (world.private / name).exists():
        return False, "private copy should be removed after publish"
    return True, "upload scanned and published"


async def save_private(filename: str, data: bytes | str) -> str:
    await checkpoint("storage.save_private")
    world = get_world()
    path = world.private / Path(filename).name
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return str(path)


async def write_public_temp(filename: str, data: bytes | str) -> str:
    await checkpoint("storage.write_public_temp")
    world = get_world()
    path = world.public / Path(filename).name
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return str(path)


async def scan_file(path: str) -> bool:
    await checkpoint("scanner.scan_file")
    world = get_world()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    world.scan_log.append(p.name)
    return True


async def publish(filename: str) -> str:
    await checkpoint("storage.publish")
    world = get_world()
    name = Path(filename).name
    src = world.private / name
    dst = world.public / name
    if not src.exists():
        raise FileNotFoundError(str(src))
    dst.write_bytes(src.read_bytes())
    src.unlink()
    return str(dst)


async def read_file(path: str) -> bytes:
    await checkpoint("storage.read_file")
    return Path(path).read_bytes()


async def rollback_upload(filename: str) -> None:
    """Remove partial upload state. Mutations run before the checkpoint so cancel is still clean."""
    world = get_world()
    name = Path(filename).name
    for folder in (world.private, world.public):
        p = folder / name
        if p.exists():
            p.unlink()
        for tmp in folder.glob(f"{name}.*"):
            if tmp.is_file():
                tmp.unlink()
    world.scan_log = [s for s in world.scan_log if s != name]
    await checkpoint("storage.rollback_upload")
