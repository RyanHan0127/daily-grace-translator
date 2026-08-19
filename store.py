"""Where finished translations live.

    translations/
      ru/2026-08-02.txt
      en/2026-08-02.txt
      ko/2026-07-27.txt

One folder per language so each reading archive stays in plain date order
instead of interleaving languages.

Everything that produces a translation goes through `translation_path` so the
web UI and the terminal share one cache -- a day translated by either is
instantly available to the other.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRANSLATIONS = HERE / "translations"

# Files this project used to write directly beside the scripts:
# 2026-08-02-ru.txt, 2026-08-02-zh-CN.txt. Deliberately strict, so unrelated
# .txt files -- including hand-kept ones like 2026-08-02-ru-claude.txt -- are
# left exactly where they are.
LEGACY_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z]{2}(?:-[A-Z]{2})?)\.txt$")


FINGERPRINTS = ".sources.json"


def translation_path(date_label: str, code: str) -> Path:
    return TRANSLATIONS / code / f"{date_label}.txt"


def fingerprint(source_text: str) -> str:
    """Short digest of the cleaned English a translation was made from."""
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()[:16]


def _fingerprints(code: str) -> dict:
    path = TRANSLATIONS / code / FINGERPRINTS
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass  # Corrupt index just means everything re-translates once.
    return {}


def _record(code: str, date_label: str, digest: str) -> None:
    path = TRANSLATIONS / code / FINGERPRINTS
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _fingerprints(code)
    data[date_label] = digest
    path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


def read(date_label: str, code: str, digest: str | None = None) -> str | None:
    """Cached translation, or None if it's missing or out of date.

    `digest` is the fingerprint of the English this translation should have
    been built from. When it doesn't match what was recorded, the cleaning
    rules have changed since -- so the cached file is stale and gets rebuilt.
    Comparing paragraph counts is not enough: an edit inside a paragraph (the
    "This devotional is taken from the book ..." credit, say) leaves the count
    identical while changing the text.

    Files written before fingerprints existed have no record, so they miss
    once and are regenerated.
    """
    path = translation_path(date_label, code)
    if not path.is_file():
        return None
    if digest is not None and _fingerprints(code).get(date_label) != digest:
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def write(date_label: str, code: str, text: str,
          digest: str | None = None) -> Path:
    path = translation_path(date_label, code)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if digest is not None:
        _record(code, date_label, digest)
    return path


def migrate_legacy() -> int:
    """Move old flat-layout files into translations/<lang>/.

    Never deletes and never overwrites: if a destination already exists, the
    old file is left alone rather than assumed redundant.
    """
    moved = 0
    for path in HERE.glob("*.txt"):
        match = LEGACY_NAME.match(path.name)
        if not match:
            continue
        target = translation_path(match.group(1), match.group(2))
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        path.replace(target)
        moved += 1
    return moved
