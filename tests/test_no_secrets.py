"""Fails if a credential is committed (or about to be). Real values belong in the git-ignored .env."""
import re
import subprocess

from trader.config import ROOT, parse_env_file

# Patterns are split so this file doesn't match itself.
PATTERNS = {
    "Telegram bot token": re.compile(r"\b\d{8,10}:" + r"[A-Za-z0-9_-]{35}\b"),
    "Google API key": re.compile("AIza" + r"[0-9A-Za-z_\-]{35}"),
    "JSON Web Token": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\." + r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
}
ROOT_ONLY_SKIPS = {".git", "venv", ".venv", "data", "logs"}  # top-level folders that are never committed


def repository_files():
    """Tracked plus untracked-but-not-ignored files (what the next commit could contain)."""
    try:
        listing = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                 cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [ROOT / line for line in listing.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        files = []
        for path in ROOT.rglob("*"):
            parts = path.relative_to(ROOT).parts
            if path.is_file() and parts[0] not in ROOT_ONLY_SKIPS and "__pycache__" not in parts:
                files.append(path)
        return files


def test_no_credentials_in_repository_files():
    findings = []
    for path in repository_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary file
        findings += [f"{path.relative_to(ROOT)}: {label}" for label, rx in PATTERNS.items() if rx.search(text)]
    assert not findings, "Credentials found; move them to .env and rotate them: " + "; ".join(findings)


def test_env_example_lists_names_only():
    """.env.example is committed, so it must never hold real values (those go in the git-ignored .env)."""
    filled = sorted(name for name, value in parse_env_file(ROOT / ".env.example").items() if value)
    assert not filled, f".env.example has values for {', '.join(filled)}: move them to .env and leave them blank here"
