#!/usr/bin/env bash
# Install the /daily-grace command on macOS or Linux.
#
#   ./install.sh            # default language: Russian
#   ./install.sh Spanish    # any language you like
#
# Safe to re-run; it overwrites the installed command with a fresh copy.

set -euo pipefail

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LANGUAGE="${1:-Russian}"
COMMANDS_DIR="$HOME/.claude/commands"
TARGET="$COMMANDS_DIR/daily-grace.md"
TEMPLATE="$PKG_DIR/command-template.md"

say() { printf '%s\n' "$*"; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ -f "$TEMPLATE" ] || fail "command-template.md not found next to this script."

# --- Python ---------------------------------------------------------------
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
      PYTHON="$candidate"
      break
    fi
  fi
done
[ -n "$PYTHON" ] || fail "Python 3.9+ not found. On macOS: brew install python3"
say "python:   $PYTHON ($("$PYTHON" --version 2>&1))"

# --- Clipboard ------------------------------------------------------------
if [ "$(uname -s)" = "Darwin" ]; then
  command -v pbcopy >/dev/null 2>&1 || say "warning: pbcopy missing (unexpected on macOS)"
else
  command -v wl-copy >/dev/null 2>&1 || command -v xclip >/dev/null 2>&1 || \
    command -v xsel >/dev/null 2>&1 || \
    say "warning: no clipboard tool found. Install one: sudo apt install xclip"
fi

# --- Install the command --------------------------------------------------
mkdir -p "$COMMANDS_DIR"
# `|` as the sed delimiter so directory slashes don't need escaping.
sed -e "s|{{PKG_DIR}}|$PKG_DIR|g" \
    -e "s|{{PYTHON}}|$PYTHON|g" \
    -e "s|{{LANGUAGE}}|$LANGUAGE|g" \
    "$TEMPLATE" > "$TARGET"
say "command:  $TARGET"
say "language: $LANGUAGE"

# --- Credentials ----------------------------------------------------------
if [ ! -f "$PKG_DIR/.env" ]; then
  cp "$PKG_DIR/.env.example" "$PKG_DIR/.env"
  # Blank out the address so the new user fills in their own.
  sed -i.bak -e 's|^GMAIL_ADDRESS=.*|GMAIL_ADDRESS=|' "$PKG_DIR/.env" && rm -f "$PKG_DIR/.env.bak"
  chmod 600 "$PKG_DIR/.env"
  say ""
  say "Created $PKG_DIR/.env — you still need to fill it in:"
  say "  1. Enable 2-Step Verification: https://myaccount.google.com/signinoptions/two-step-verification"
  say "  2. Create an App Password:     https://myaccount.google.com/apppasswords"
  say "  3. Put your address and that password into .env"
  say "  4. Gmail -> Settings -> Forwarding and POP/IMAP -> Enable IMAP"
else
  chmod 600 "$PKG_DIR/.env"
  say "env:      $PKG_DIR/.env (left as-is)"
fi

# Zip archives built on Windows don't carry the executable bit.
chmod +x "$PKG_DIR/start.command" 2>/dev/null || true

# macOS quarantines anything downloaded from the internet; for scripts it
# surfaces as "is damaged and can't be opened", which right-click -> Open does
# not clear. Strip it so start.command just works.
if command -v xattr >/dev/null 2>&1; then
  xattr -cr "$PKG_DIR" 2>/dev/null || true
  say "quarantine: cleared"
fi

say ""
say "Done. Once .env is filled in, start the app with:"
say "  open \"$PKG_DIR/start.command\"      (or just double-click it)"
say ""
say "No-UI alternatives:"
say "  $PYTHON \"$PKG_DIR/daily_grace.py\"   # terminal, prints + copies"
say "  /daily-grace                          # inside Claude Code"
