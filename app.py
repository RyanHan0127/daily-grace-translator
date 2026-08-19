"""Local web UI for the daily devotional.

    python3 app.py

Starts a server on 127.0.0.1 and opens a browser. One button fetches the last
seven days of emails, translates them, and shows them as an archive.

Stdlib only -- no Flask, no pip install.

Security note: this deliberately does NOT serve the package directory. `.env`
lives there and holds a Gmail App Password, so routes are whitelisted one by
one and everything else 404s. The server also binds to loopback only, so it is
not reachable from the network.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import daily_grace
import fetch_daily_grace
import store
import translate as translator
from fetch_daily_grace import FetchError

HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.html"
HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# A friendlier address for the same server. `.localhost` is reserved for
# loopback (RFC 6761) and Chrome, Edge, Opera, Brave and Firefox resolve any
# name under it internally -- no hosts file, no admin rights. Safari does not:
# it defers to the system resolver, which has no wildcard entry. So the plain
# IP stays the default and this is opt-in via --pretty.
#
# Set DAILY_GRACE_HOSTNAME to anything you've pointed at 127.0.0.1 yourself in
# /etc/hosts (or Windows\System32\drivers\etc\hosts), e.g. daily-grace.me.
PRETTY_HOST = os.environ.get("DAILY_GRACE_HOSTNAME", "daily-grace.localhost")

DEFAULT_DAYS = 7
MAX_DAYS = 30

# Short blocks near the top are the reference / date / title lines.
META_MAX = 80
SCRIPTURE_MIN = 120


split_blocks = daily_grace.split_blocks
looks_like_reference = daily_grace.looks_like_reference


def structure(translated: str, english: str) -> dict:
    """Split the translated text into scripture / heading lines / body.

    The newsletter's layout is consistent -- scripture, reference, date, title,
    then body -- but it can only be recognised reliably on the *English* text.
    Translated text shifts length (Russian runs longer than English, and some
    scripture quotes are shorter than any sane threshold), so detecting by size
    on the translation mislabels the date as the title, or finds nothing at all.

    So: locate the structure in English, then apply those positions to the
    translated blocks. Chunking preserves paragraph breaks, so the two line up;
    if they ever don't, the block counts disagree and we fall back.
    """
    blocks = split_blocks(translated)
    if not blocks:
        return {"scripture": "", "meta": [], "body": [], "title": ""}

    source = split_blocks(english)

    if (len(source) == len(blocks) and len(source) >= 5
            and looks_like_reference(source[1]) and len(source[2]) <= 40):
        return {
            "scripture": blocks[0],
            "meta": blocks[1:4],       # reference, date, title
            "body": blocks[4:],
            "title": blocks[3],
        }

    # Unfamiliar layout: fall back to sizing the translated text, and let the
    # caller supply a title from the subject line if this finds none.
    scripture = ""
    index = 0
    if len(blocks[0]) >= SCRIPTURE_MIN:
        scripture = blocks[0]
        index = 1

    meta: list[str] = []
    while index < len(blocks) and len(blocks[index]) <= META_MAX and len(meta) < 3:
        meta.append(blocks[index])
        index += 1

    return {
        "scripture": scripture,
        "meta": meta,
        "body": blocks[index:],
        "title": meta[-1] if meta else "",
    }


def title_from_subject(subject: str) -> str:
    """'Daily Grace Inspiration: Some Title' -> 'Some Title'."""
    _, sep, tail = subject.partition(":")
    return (tail if sep else subject).strip()


def translate_day(message: dict, code: str, api_key: str | None) -> dict:
    """Translate one day, reusing an existing file when there is one.

    Caching matters: seven days through the free endpoint is slow, and after
    the first run only the newest day is actually new.
    """
    date_label = message["date_label"]

    # Always needed, cached or not: structure is detected against the English.
    cleaned = daily_grace.strip_boilerplate(message["body"])

    digest = store.fingerprint(cleaned)
    translated = store.read(date_label, code, digest)
    cached = translated is not None
    if cached:
        backend = "cached"
        out_path = store.translation_path(date_label, code)
    else:
        translated, backend = translator.translate(cleaned, code, api_key=api_key)
        out_path = store.write(date_label, code, translated, digest)

    parts = structure(translated, cleaned)
    if not parts["title"]:
        parts["title"] = title_from_subject(message.get("subject", ""))

    return {
        "date_label": date_label,
        "subject": message.get("subject", ""),
        "text": translated,
        "saved_to": str(out_path),
        "backend": backend,
        "cached": cached,
        **parts,
    }


def build(language: str, days: int) -> dict:
    days = max(1, min(days, MAX_DAYS))
    messages = fetch_daily_grace.fetch_messages(days)

    try:
        fetch_daily_grace.load_env()
    except FetchError:
        pass
    api_key = os.environ.get("GOOGLE_TRANSLATE_API_KEY", "").strip() or None

    code = translator.normalize_lang(language)

    entries: list[dict] = []
    failures: list[str] = []
    for message in messages:
        try:
            entries.append(translate_day(message, code, api_key))
        except translator.TranslationError as exc:
            # One bad day shouldn't lose the other six.
            failures.append(f"{message['date_label']}: {exc}")

    if not entries:
        raise FetchError("Could not translate any of the days. " + " / ".join(failures))

    return {
        "ok": True,
        "language": code,
        "days": entries,
        "warning": ("Some days could not be translated -- " + "; ".join(failures))
                   if failures else "",
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Keep the console clean; errors still surface in the UI.

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        route = urlparse(self.path)

        if route.path in ("/", "/index.html"):
            if not INDEX.is_file():
                self._send(500, b"index.html is missing", "text/plain; charset=utf-8")
                return
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            return

        if route.path == "/api/devotional":
            params = parse_qs(route.query)
            language = (params.get("lang") or ["Russian"])[0]
            try:
                days = int((params.get("days") or [DEFAULT_DAYS])[0])
            except ValueError:
                days = DEFAULT_DAYS
            try:
                self._json(200, build(language, days))
            except FetchError as exc:
                self._json(200, {"ok": False, "error": str(exc)})
            except translator.TranslationError as exc:
                self._json(200, {"ok": False, "error": f"Translation failed: {exc}"})
            except Exception as exc:  # noqa: BLE001 - surface anything to the UI
                self._json(200, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return

        self._send(404, b"Not found", "text/plain; charset=utf-8")


def free_port(start: int) -> int:
    for candidate in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex((HOST, candidate)) != 0:
                return candidate
    raise SystemExit(f"No free port between {start} and {start + 19}.")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    moved = store.migrate_legacy()
    if moved:
        print(f"Moved {moved} existing translation(s) into {store.TRANSLATIONS}")

    port = free_port(int(os.environ.get("DAILY_GRACE_PORT", DEFAULT_PORT)))
    pretty = f"http://{PRETTY_HOST}:{port}/"
    named = f"http://localhost:{port}/"
    numeric = f"http://{HOST}:{port}/"
    server = ThreadingHTTPServer((HOST, port), Handler)

    width = max(len(pretty), len(named), len(numeric))
    print("Daily Grace is running.")
    print(f"  {pretty:<{width}}   <- nicest; Chrome, Edge, Opera, Firefox")
    print(f"  {named:<{width}}   <- works everywhere, including Safari")
    print(f"  {numeric:<{width}}   <- if the above ever fails")
    print("Leave this window open. Press Ctrl+C to stop.")

    if "--no-browser" not in sys.argv:
        opened = pretty if "--pretty" in sys.argv else named
        threading.Timer(0.5, lambda: webbrowser.open(opened)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
