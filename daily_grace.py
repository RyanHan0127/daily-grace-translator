"""One-shot: fetch the devotional, strip the boilerplate, translate, deliver.

    python daily_grace.py                    # Russian, to file + clipboard
    python daily_grace.py -l Korean
    python daily_grace.py --no-clipboard
    python daily_grace.py --source path.txt  # re-run on an already-fetched file

No Claude Code involved. Translation goes through Google Translate -- see
translate.py for the two backends and how one is chosen.

The boilerplate stripping here is what Claude used to do by eye, reduced to
rules that fit this specific newsletter's layout. If Joseph Prince Ministries
restructures their template, this is the part that will need updating.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import deliver
import store
import translate as translator

HERE = Path(__file__).resolve().parent
FETCHER = HERE / "fetch_daily_grace.py"

# Everything from the first line matching one of these is footer. The
# pastor's note sits above them, so it survives the cut.
FOOTER_MARKERS = (
    # The sign-off note after the devotional proper. It's often a seasonal
    # message repeated verbatim for a week at a time. Matched loosely because
    # the header wraps mid-phrase in the source ("...from Pastor" / "Prince:").
    r"^\**a special note\b",
    r"note from pastor\b",
    # Product / book promotion that follows the devotional. Several spellings
    # because the section header wording changes with each campaign; the cut
    # happens at whichever appears first.
    r"^\**continue your journey",
    r"request .{0,40}new book",
    r"request yours today",
    r"for a gift of any amount",
    r"for any gift amount",
    r"today'?s offer",
    r"^\**\(?for your gift",
    r"^get offer",
    # Mailing-list furniture.
    r"^forward\b.*unsubscribe",
    r"\bunsubscribe\b",
    r"manage subscription",
    r"you are receiving this email",
    r"was this email forwarded",
    r"©\s*copyright",
    r"joseph prince ministries,\s*po box",
)

# Dropped wherever they appear above the footer.
NOISE_LINES = (
    r"^\**\s*$",              # stray **** separators
    r"^watch service here\s*$",
    r"^\s*\|\s*$",
)

URL = re.compile(r"https?://\S+")

# A paragraph that doesn't close its sentence is a fragment. The newsletter
# breaks paragraphs at bold spans, which lands mid-sentence ("...the gift of
# righteousness" / "'will reign in life...'") and sometimes straight after an
# opening quote ('the enemy is quick to whisper, "').
#
# A colon counts as closing, so section headers like "A Special Note from
# Pastor Prince:" stay on their own line instead of swallowing the paragraph
# beneath them.
SENTENCE_END = re.compile(r"[.!?:…][\"”’')\]]*$")
OPEN_QUOTE_END = re.compile(r"[“\"]$")

# The book credit tacked onto the final paragraph: "This devotional is taken
# from the book <Title>." Unlike the promo blocks this is an inline sentence,
# so it has to be cut out rather than truncated at. No observed book title
# contains a full stop, so stopping at the first one is safe.
SOURCE_CREDIT = re.compile(
    r"\s*This\s+(?:devotional|reading|excerpt|article|message)\s+is\s+"
    r"(?:taken|adapted|excerpted)\s+from\b[^.!?]*[.!?]",
    re.IGNORECASE,
)


def split_blocks(text: str) -> list[str]:
    return [b.strip() for b in text.split("\n\n") if b.strip()]


def looks_like_reference(block: str) -> bool:
    """'Mark 2:5, 10-12', 'Romans 5:17', 'John 14:13' -- chapter:verse."""
    return len(block) <= 60 and bool(re.search(r"\d+\s*:\s*\d+", block))


def heading_count(blocks: list[str]) -> int:
    """How many leading blocks are scripture / reference / date / title.

    Returns 0 when the familiar shape isn't there, which keeps the fragment
    joining below from running on a layout it doesn't understand.
    """
    if (len(blocks) >= 5 and looks_like_reference(blocks[1])
            and len(blocks[2]) <= 40):
        return 4
    return 0


def reflow(block: str) -> list[str]:
    """Split one blank-line-delimited block into its actual paragraphs.

    Two line conventions show up in these emails, sometimes in the same one:

      * hard wrapping, where a line stops mid-sentence and the next continues
        it ("...sprinkled with His" / "blood from an evil conscience.")
      * one line per paragraph, with only a single newline between them and no
        blank line at all

    Splitting on blank lines alone turns the second case into a single
    3,000-character wall of text. So: a line that ends a sentence ends a
    paragraph, and a line that doesn't is a wrap and gets joined on.
    """
    paragraphs: list[str] = []
    current = ""

    for line in block.split("\n"):
        line = " ".join(line.split())
        if not line:
            continue
        if not current:
            current = line
        elif SENTENCE_END.search(current):
            paragraphs.append(current)
            current = line
        else:
            current = f"{current} {line}"

    if current:
        paragraphs.append(current)
    return paragraphs


def join_fragments(blocks: list[str]) -> list[str]:
    """Glue continuation blocks back onto the paragraph they belong to."""
    merged: list[str] = []
    for block in blocks:
        if merged and not SENTENCE_END.search(merged[-1]):
            # No space after an opening quote: 'whisper, "How can...'
            separator = "" if OPEN_QUOTE_END.search(merged[-1]) else " "
            merged[-1] = merged[-1] + separator + block
        else:
            merged.append(block)
    return merged


def strip_boilerplate(text: str) -> str:
    lines = text.split("\n")
    footer = re.compile("|".join(FOOTER_MARKERS), re.IGNORECASE)
    noise = re.compile("|".join(NOISE_LINES), re.IGNORECASE)

    kept: list[str] = []
    for line in lines:
        if footer.search(line):
            break

        stripped = line.strip()
        # Blank lines are the only paragraph structure the email has, so they
        # must survive; the noise patterns below would otherwise eat them.
        if not stripped:
            kept.append("")
            continue
        if URL.fullmatch(stripped):
            continue

        text = URL.sub("", line).strip()
        # Markdown-ish emphasis the HTML-to-text pass leaves behind.
        text = re.sub(r"\*{2,}", "", text).strip()
        if not text or noise.match(text):
            continue
        kept.append(text)

    # Rejoin each paragraph's hard-wrapped lines into one line. Blocks are
    # separated by blank lines, so headings and the scripture reference stay
    # on their own.
    blocks = []
    for chunk in re.split(r"\n\s*\n", "\n".join(kept)):
        blocks.extend(reflow(chunk))
    blocks = [SOURCE_CREDIT.sub("", b).strip() for b in blocks]
    blocks = [b for b in blocks if b]

    # Repair paragraphs the newsletter split at bold spans -- but only below
    # the headings, which legitimately end without punctuation.
    headings = heading_count(blocks)
    if headings:
        blocks = blocks[:headings] + join_fragments(blocks[headings:])

    body = "\n\n".join(blocks)

    # The source HTML sometimes runs paragraphs together with no separator at
    # all ("...not well!Some Christians...", '...diseases."Not so long ago').
    # A sentence-ending mark flush against a capital is never valid prose, so
    # it is a safe split point. The lookbehind avoids splitting initialisms
    # like "U.S.A".
    body = re.sub(r'(?<![A-Z])([.!?]["\u201d\u2019\']?)([A-Z])',
                  "\\1\n\n\\2", body)

    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def fetch(source: Path | None) -> tuple[str, str, dict]:
    """Return (text, date_label, metadata)."""
    if source:
        label = re.sub(r"^source-", "", source.stem)
        return source.read_text(encoding="utf-8"), label, {"source": str(source)}

    result = subprocess.run(
        [sys.executable, str(FETCHER)],
        capture_output=True, text=True, encoding="utf-8",
    )

    line = (result.stdout or "").strip().splitlines()
    if not line:
        raise SystemExit(
            "The fetcher produced no output.\n"
            + (result.stderr or "").strip()
        )

    try:
        info = json.loads(line[-1])
    except ValueError:
        raise SystemExit(
            "Could not parse the fetcher's output:\n"
            + (result.stdout or "") + (result.stderr or "")
        )

    if not info.get("ok"):
        raise SystemExit(f"Fetch failed: {info.get('error', 'unknown error')}")

    path = Path(info["source_path"])
    return path.read_text(encoding="utf-8"), info["date_label"], info


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-l", "--language", default="Russian")
    parser.add_argument("--no-clipboard", action="store_true")
    parser.add_argument("--source", type=Path,
                        help="Use an already-fetched text file instead of Gmail.")
    parser.add_argument("--fresh", action="store_true",
                        help="Re-translate even if this day is already cached.")
    args = parser.parse_args()

    raw, date_label, info = fetch(args.source)
    if info.get("subject"):
        print(f"email:      {info['subject']}")

    cleaned = strip_boilerplate(raw)
    print(f"devotional: {len(cleaned)} chars (from {len(raw)} raw)")
    if len(cleaned) < 200:
        print("warning: that is suspiciously short -- the email template may "
              "have changed. Check the raw text before trusting this.")

    # Read the optional API key the same way the fetcher reads credentials.
    import fetch_daily_grace  # noqa: E402  (imported for its .env loading)
    try:
        fetch_daily_grace.load_env()
    except fetch_daily_grace.FetchError:
        pass  # Missing Gmail creds don't matter when --source was used.
    import os
    api_key = os.environ.get("GOOGLE_TRANSLATE_API_KEY", "").strip() or None

    code = translator.normalize_lang(args.language)

    # Shared with the web UI, so a day translated in either is ready in both.
    digest = store.fingerprint(cleaned)
    translated = None if args.fresh else store.read(date_label, code, digest)
    if translated is not None:
        backend = "cached"
        out_path = store.translation_path(date_label, code)
    else:
        try:
            translated, backend = translator.translate(cleaned, code, api_key=api_key)
        except translator.TranslationError as exc:
            raise SystemExit(f"Translation failed: {exc}")
        out_path = store.write(date_label, code, translated, digest)

    print(f"translated: -> {code} via {backend} backend")
    print(f"saved:      {out_path}")

    if not args.no_clipboard:
        try:
            tool = deliver.copy_text(translated)
            print(f"clipboard:  copied via {tool}")
        except Exception as exc:
            print(f"clipboard:  FAILED ({exc}) -- the file above still has it")

    print()
    print(translated)


if __name__ == "__main__":
    main()
