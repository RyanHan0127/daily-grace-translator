"""Google Translate backends. Stdlib only.

Two backends, picked automatically:

  * `official` -- Google Cloud Translation API v2. Used when
    GOOGLE_TRANSLATE_API_KEY is set. Documented, stable, and the free tier
    (500K characters/month) is far more than this ever needs.
  * `free` -- the undocumented endpoint that translate.google.com's own web
    client calls. No key, no signup. It is not a supported API: Google can
    change or rate-limit it without notice, so treat breakage as expected
    rather than surprising.

Both chunk on paragraph boundaries; long requests get truncated or rejected.
"""

from __future__ import annotations

import html
import json
import urllib.error
import urllib.parse
import urllib.request

# Google's own limit is higher, but short requests are less likely to be
# throttled and paragraph-sized chunks translate better anyway.
MAX_CHUNK = 3500

LANGUAGES = {
    "english": "en", "en": "en", "original": "en",
    "russian": "ru", "ru": "ru",
    "spanish": "es", "es": "es",
    "korean": "ko", "ko": "ko",
    "chinese": "zh-CN", "mandarin": "zh-CN", "zh": "zh-CN",
    "simplified chinese": "zh-CN", "zh-cn": "zh-CN",
    "traditional chinese": "zh-TW", "zh-tw": "zh-TW",
    "japanese": "ja", "ja": "ja",
    "french": "fr", "fr": "fr",
    "german": "de", "de": "de",
    "portuguese": "pt", "pt": "pt",
    "indonesian": "id", "id": "id",
    "tagalog": "tl", "filipino": "tl", "tl": "tl",
    "vietnamese": "vi", "vi": "vi",
    "thai": "th", "th": "th",
    "hindi": "hi", "hi": "hi",
    "arabic": "ar", "ar": "ar",
    "italian": "it", "it": "it",
    "polish": "pl", "pl": "pl",
    "ukrainian": "uk", "uk": "uk",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


class TranslationError(RuntimeError):
    pass


def normalize_lang(name: str) -> str:
    """'Russian' -> 'ru'. Unknown values pass through unchanged so that any
    valid ISO code still works even if it isn't in the table above."""
    key = (name or "").strip().lower()
    return LANGUAGES.get(key, key)


def chunk(text: str, limit: int = MAX_CHUNK) -> list[str]:
    """Split on blank lines, never mid-paragraph.

    A single paragraph longer than the limit is passed through whole rather
    than cut mid-sentence -- a slightly oversized request beats a mangled one.
    """
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = para

    if current:
        chunks.append(current)
    return chunks


def _post(url: str, data: bytes | None, headers: dict) -> bytes:
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise TranslationError(f"HTTP {exc.code} from {url.split('?')[0]}: {detail}")
    except urllib.error.URLError as exc:
        raise TranslationError(f"Network error reaching Google: {exc.reason}")


def translate_official(text: str, target: str, source: str, api_key: str) -> str:
    url = "https://translation.googleapis.com/language/translate/v2"
    payload = urllib.parse.urlencode({
        "key": api_key,
        "q": text,
        "target": target,
        "source": source,
        "format": "text",
    }).encode("utf-8")

    raw = _post(url, payload, {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    })

    try:
        body = json.loads(raw)
        translated = body["data"]["translations"][0]["translatedText"]
    except (ValueError, KeyError, IndexError) as exc:
        raise TranslationError(f"Unexpected response from Google API: {exc}")

    # Returned text is HTML-escaped even with format=text.
    return html.unescape(translated)


def translate_free(text: str, target: str, source: str) -> str:
    query = urllib.parse.urlencode({
        "client": "gtx",
        "sl": source,
        "tl": target,
        "dt": "t",
        "q": text,
    })
    url = f"https://translate.googleapis.com/translate_a/single?{query}"

    raw = _post(url, None, {"User-Agent": USER_AGENT})

    try:
        body = json.loads(raw)
        # Shape: [[[translated, original, ...], [translated, original, ...]], ...]
        segments = [seg[0] for seg in body[0] if seg and seg[0]]
    except (ValueError, IndexError, TypeError) as exc:
        raise TranslationError(
            f"Could not parse the free endpoint's response ({exc}). It may have "
            "changed or rate-limited you; set GOOGLE_TRANSLATE_API_KEY to use "
            "the official API instead."
        )

    return "".join(segments)


def translate(text: str, target: str, source: str = "en",
              api_key: str | None = None) -> tuple[str, str]:
    """Translate `text`, returning (translated_text, backend_used)."""
    target = normalize_lang(target)
    if not target:
        raise TranslationError("No target language given.")

    # Asking for the language it's already in: hand back the cleaned original.
    # No network call, nothing to fail, nothing to get wrong.
    if target == normalize_lang(source):
        return text, "original"

    backend = "official" if api_key else "free"
    pieces = []

    for piece in chunk(text):
        if not piece.strip():
            pieces.append(piece)
            continue
        if api_key:
            pieces.append(translate_official(piece, target, source, api_key))
        else:
            pieces.append(translate_free(piece, target, source))

    return "\n\n".join(pieces), backend
