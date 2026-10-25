"""What processed a run: the checked-out commit, and SHA-256 digests of the trader package's source and of
config/*.toml. The daily run records them with each run (the runs table), so every session of the unattended record
names exactly the code and configuration behind it, uncommitted changes included. Files are only read: no git
process is started (a scheduled task runs windowless, and a console window popping up is how a run was once killed).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from trader.config import ROOT


def digest(files: list[Path], root: Path) -> str:
    """SHA-256 over each file's path (relative to `root`) and bytes, in path order."""
    h = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        h.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def commit(root: Path = ROOT) -> str:
    """The commit .git/HEAD points at (a branch's, or a detached one); '' when it can't be read."""
    git = root / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head
        ref = head[5:]
        if (git / ref).is_file():
            return (git / ref).read_text(encoding="utf-8").strip()
        for line in (git / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split(" ", 1)[0]
    except OSError:
        pass
    return ""


def provenance(root: Path = ROOT) -> tuple[str, str]:
    """(code, config): "<commit> src <digest>" and the configuration's digest, for the runs table."""
    source = digest([p for p in (root / "trader").rglob("*.py") if "__pycache__" not in p.parts], root)
    config = digest(list((root / "config").glob("*.toml")), root)
    return f"{commit(root)[:12] or 'unknown'} src {source[:16]}", config[:16]
