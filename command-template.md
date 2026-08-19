---
description: Find the latest "Daily Grace Inspiration" email in Gmail and produce a translated, copy-ready text
argument-hint: "[language] (default: {{LANGUAGE}})"
allowed-tools: Bash, PowerShell, Read, Write
---

Fetch the most recent **Daily Grace Inspiration** devotional from Gmail, translate it, and leave the result on the clipboard ready to paste.

**Target language:** $1 — if empty, use **{{LANGUAGE}}**.

## Step 1 — Fetch

```
{{PYTHON}} "{{PKG_DIR}}/fetch_daily_grace.py"
```

The script pulls the newest email from `no-reply@josephprince.org` with subject `Daily Grace Inspiration` over IMAP, opens the mailbox read-only (so it never marks the mail as read), writes the plain text to a UTF-8 file, and prints a JSON summary.

It prints exactly one JSON object. On success: `ok: true` plus `subject`, `date_label`, `matches`, `chars`, and `source_path`. On failure: `ok: false` and an `error`.

If `ok` is false, show the user the `error` verbatim and stop — do not improvise a different sender, subject, or source. The common cases:

- **Missing credentials** — walk them through Step 0 in `{{PKG_DIR}}/README.md`. They must generate the App Password and write the `.env` themselves; never ask them to paste it into chat, and never type a password into any field on their behalf.
- **Login rejected** — usually the account password was used instead of an App Password, 2-Step Verification is off, or IMAP is disabled in Gmail settings.
- **No email found** — say so plainly. Do not fall back to an older devotional or a different newsletter.

## Step 2 — Read and isolate

`Read` the file at `source_path`.

It is the whole email body, boilerplate included. Keep only the devotional: the title, the scripture reference and verse text, the body paragraphs, and any closing line or prayer.

Drop the wrapper: `View in browser`, `Unsubscribe`, `Privacy Policy`, social links, mailing address, and the `© <year> Joseph Prince Ministries` line.

Sanity-check before translating. If the text looks truncated mid-sentence, or `chars` is implausibly small (under ~200), say so rather than translating a fragment as if it were whole.

## Step 3 — Translate

Translate the isolated text into the target language.

- Preserve the structure and line breaks — title on its own line, scripture reference and verse as their own block, body paragraphs kept separate.
- Render the scripture **reference** using the target language's conventional book names and versification (Russian: `Евреям 4:9-10`, not a transliteration of "Hebrews").
- Translate the verse's sense faithfully rather than pasting in an unrelated published translation. If the source names its version (NKJV, NLT, …), keep that in parentheses after the reference.
- Match the register of the original: warm and devotional, not clinical.
- Translate the whole thing. No summarizing, no added commentary, no greetings that weren't in the source.

## Step 4 — Deliver

`Write` the translation to:

```
{{PKG_DIR}}/translations/<lang>/<date_label>.txt
```

Use `date_label` from the JSON — the email's own date, not today's — so re-running against an older email doesn't overwrite the wrong day. `<lang>` is the short code (`ru`, `ko`, `es`), matching what the app writes, so the web UI picks your translation up as its cached copy for that day.

Create the language folder if it isn't there yet.

Then copy it to the clipboard:

```
{{PYTHON}} "{{PKG_DIR}}/deliver.py" "{{PKG_DIR}}/translations/<lang>/<date_label>.txt"
```

This prints `ok: true` with a `chars` count. If it reports `ok: false`, tell the user — the file is still on disk, so they can open it directly.

Finally, print the full translated text in the chat in a fenced code block, and confirm on one line that it's on the clipboard, plus the file path and the email's date.
