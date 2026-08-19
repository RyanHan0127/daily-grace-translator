"""Fetch 'Daily Grace Inspiration' emails from Gmail over IMAP.

As a script it prints a JSON summary of the newest one and writes its text to
`.cache/source-<date>.txt`:

    python fetch_daily_grace.py

As a library, `fetch_messages(count)` returns the newest `count` days, newest
first, for callers that want the archive (see app.py).

Credentials come from the environment, or from a `.env` file sitting next to
this script:

    GMAIL_ADDRESS=you@gmail.com
    GMAIL_APP_PASSWORD=abcd efgh ijkl mnop

The app password is a 16-character Google App Password, not your account
password. Requires 2-Step Verification to be enabled on the account.
"""

from __future__ import annotations

import email
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

SENDER = "no-reply@josephprince.org"
SUBJECT = "Daily Grace Inspiration"

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache"

# Mailbox candidates, in order. All Mail catches archived copies; the
# localized names cover non-English account locales.
MAILBOXES = ['"[Gmail]/All Mail"', '"[Google Mail]/All Mail"', "INBOX"]

EPOCH = datetime.min.replace(tzinfo=timezone.utc)


class FetchError(RuntimeError):
    """Anything that should reach the user as a readable sentence."""


def load_env() -> tuple[str, str]:
    """Read credentials from the environment, falling back to a local .env."""
    env_file = HERE / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

    address = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

    if not address or not password:
        raise FetchError(
            "Missing credentials. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD as "
            f"environment variables, or create {env_file} containing them. "
            "GMAIL_APP_PASSWORD must be a Google App Password "
            "(https://myaccount.google.com/apppasswords), not your login password."
        )

    # Google displays app passwords in groups of four; the spaces are cosmetic
    # and IMAP rejects them.
    return address, password.replace(" ", "")


def die(message: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    sys.exit(code)


class TextExtractor(HTMLParser):
    """Minimal HTML -> text conversion. No external dependencies."""

    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
             "table", "blockquote", "section", "header", "footer"}

    # Tags whose contents are not readable text. Only tags that actually have
    # a closing tag may appear here: the counter below waits for one, and a
    # void element like <meta> would suppress the entire rest of the document.
    SKIP = {"script", "style", "title"}

    # Never adjust the skip counter for these -- HTML5 allows them unclosed.
    VOID = {"meta", "link", "br", "img", "hr", "input", "area", "base",
            "col", "embed", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._suppress = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            if tag in self.BLOCK:      # <br>
                self.parts.append("\n")
            return
        if tag in self.SKIP:
            self._suppress += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if tag in self.SKIP:
            self._suppress = max(0, self._suppress - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._suppress:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def tidy(text: str) -> str:
    """Normalize whitespace without destroying paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("‌", "").replace("​", "")
    # Collapse runs of spaces/tabs, but leave newlines alone.
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    # At most one blank line between paragraphs.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def decode_part(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def body_of(message) -> str:
    """Prefer the HTML part; fall back to text/plain.

    The plain-text alternative these emails ship is hard-wrapped at roughly
    1000 characters with no blank line between paragraphs, so a whole
    devotional can collapse into one unreadable block -- 2026-07-07 arrives as
    a single 2300-character paragraph that way. The HTML keeps its <p> and
    <div> boundaries, which survive extraction. Measured over 30 days, HTML
    gave more paragraphs on 23 and fewer on none, with the same text.

    The fallback matters: if a template ever defeats the extractor, a short or
    empty result means we use the plain part rather than lose the devotional.
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []

    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if "attachment" in str(part.get("Content-Disposition", "")).lower():
            continue
        if part.get_content_type() == "text/plain":
            plain_parts.append(decode_part(part))
        elif part.get_content_type() == "text/html":
            html_parts.append(decode_part(part))

    plain = tidy("\n".join(plain_parts)) if plain_parts else ""

    html = ""
    if html_parts:
        extractor = TextExtractor()
        extractor.feed("\n".join(html_parts))
        html = tidy(extractor.text())

    if html and (not plain or len(html) >= len(plain) * 0.6):
        return html
    return plain


def header(message, name: str) -> str:
    raw = message.get(name)
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except Exception:
        return str(raw).strip()


def sent_at(message) -> datetime:
    try:
        parsed = parsedate_to_datetime(message.get("Date"))
    except Exception:
        return EPOCH
    if parsed is None:
        return EPOCH
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def open_mailbox():
    """Log in and select a mailbox read-only. Returns (imap, mailbox_name)."""
    address, password = load_env()

    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    except Exception as exc:
        raise FetchError(f"Could not reach imap.gmail.com: {exc}")

    try:
        imap.login(address, password)
    except imaplib.IMAP4.error as exc:
        # imaplib wraps the server's reply as bytes; showing its repr to
        # someone reading this in the UI is just noise.
        detail = exc.args[0] if exc.args else str(exc)
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        imap.logout()
        raise FetchError(
            f"Gmail rejected the login: {detail}. Check that the address is "
            "correct, that 2-Step Verification is on, that the value is an "
            "App Password rather than your account password, and that IMAP "
            "is enabled in Gmail settings."
        )

    for mailbox in MAILBOXES:
        # readonly so fetching never marks the devotional as read.
        status, _ = imap.select(mailbox, readonly=True)
        if status == "OK":
            return imap, mailbox

    imap.logout()
    raise FetchError("Could not open any Gmail mailbox (tried All Mail and INBOX).")


def search_ids(imap) -> list[bytes]:
    # Both values must be quoted: the subject contains spaces, and an unquoted
    # multi-word atom makes Gmail reject the whole command with BAD
    # "Could not parse command".
    try:
        status, data = imap.search(
            None, "FROM", f'"{SENDER}"', "SUBJECT", f'"{SUBJECT}"'
        )
    except imaplib.IMAP4.error as exc:
        raise FetchError(f"IMAP search failed: {exc}")
    if status != "OK":
        raise FetchError(f"IMAP search failed: {status}")
    return data[0].split()


def fetch_messages(count: int = 1) -> list[dict]:
    """Return the newest `count` devotionals, newest first.

    One entry per calendar day -- if a day somehow has two, the later one wins,
    since the UI keys its archive by date.
    """
    imap, mailbox = open_mailbox()
    try:
        ids = search_ids(imap)
        if not ids:
            raise FetchError(
                f"No email found from {SENDER} with subject "
                f"'{SUBJECT}' in {mailbox}."
            )

        # Sequence order usually tracks arrival, but fetch a few extra and sort
        # by Date header so an out-of-order delivery can't skew the result.
        candidates = ids[-(count + 3):]
        loaded: list[tuple[datetime, object]] = []
        for msg_id in candidates:
            status, raw = imap.fetch(msg_id, "(RFC822)")
            if status != "OK" or not raw or not isinstance(raw[0], tuple):
                continue
            message = email.message_from_bytes(raw[0][1])
            loaded.append((sent_at(message), message))

        if not loaded:
            raise FetchError("Found matching messages but could not fetch any of them.")

        loaded.sort(key=lambda pair: pair[0], reverse=True)

        CACHE.mkdir(parents=True, exist_ok=True)
        results: list[dict] = []
        seen_days: set[str] = set()

        for when, message in loaded:
            if len(results) >= count:
                break

            body = body_of(message)
            if not body:
                continue

            label = (when if when != EPOCH else datetime.now(timezone.utc)).strftime("%Y-%m-%d")
            if label in seen_days:
                continue
            seen_days.add(label)

            path = CACHE / f"source-{label}.txt"
            path.write_text(body, encoding="utf-8")

            results.append({
                "subject": header(message, "Subject"),
                "from": header(message, "From"),
                "date": when.isoformat() if when != EPOCH else None,
                "date_label": label,
                "mailbox": mailbox,
                "matches": len(ids),
                "chars": len(body),
                "source_path": str(path),
                "body": body,
            })

        if not results:
            raise FetchError("Fetched the emails but could not extract text from any.")

        return results
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        newest = fetch_messages(1)[0]
    except FetchError as exc:
        die(str(exc))
        return

    # `body` is on disk already; keep it out of the JSON line.
    summary = {"ok": True, **{k: v for k, v in newest.items() if k != "body"}}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
