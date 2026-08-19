#!/usr/bin/env bash
# Double-click this on macOS to open the Daily Grace app.
# The Terminal window that appears must stay open while you use it.

cd "$(dirname "$0")" || exit 1

for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$candidate" app.py
  fi
done

echo "Python 3 was not found."
echo "Install it with:  brew install python3"
echo "or from:          https://www.python.org/downloads/"
echo
read -r -p "Press Return to close."
