"""Copy a UTF-8 text file to the system clipboard, cross-platform.

    python deliver.py path/to/translation.txt

Exists so the slash command doesn't need OS-specific clipboard branching.
Cyrillic (and any other non-ASCII) survives on all three platforms, which
naive `clip.exe` piping on Windows does not manage.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def copy_windows(text: str) -> None:
    """Use the Win32 clipboard directly with CF_UNICODETEXT.

    Piping to clip.exe re-encodes through the console codepage and mangles
    non-ASCII, so go straight to the API instead.
    """
    import ctypes
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    # +1 for the terminating NUL; UTF-16LE is 2 bytes per code unit.
    data = text.encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise OSError("GlobalAlloc failed")

    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        raise OSError("GlobalLock failed")
    ctypes.memmove(pointer, data, len(data))
    kernel32.GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        raise OSError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise OSError("SetClipboardData failed")
    finally:
        user32.CloseClipboard()


def copy_unix(text: str) -> str:
    """macOS pbcopy, or one of the usual Linux clipboard helpers."""
    if sys.platform == "darwin":
        candidates = [["pbcopy"]]
    else:
        candidates = [
            ["wl-copy"],                          # Wayland
            ["xclip", "-selection", "clipboard"],  # X11
            ["xsel", "--clipboard", "--input"],
        ]

    for argv in candidates:
        if shutil.which(argv[0]):
            subprocess.run(argv, input=text.encode("utf-8"), check=True)
            return argv[0]

    names = ", ".join(c[0] for c in candidates)
    raise RuntimeError(
        f"No clipboard tool found (looked for: {names}). "
        "On Linux install one, e.g. `sudo apt install xclip`."
    )


def copy_text(text: str) -> str:
    """Copy `text` to the clipboard. Returns the tool/mechanism used."""
    if sys.platform == "win32":
        copy_windows(text)
        return "win32 clipboard"
    return copy_unix(text)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "usage: deliver.py <file>"}))
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.is_file():
        print(json.dumps({"ok": False, "error": f"No such file: {path}"},
                         ensure_ascii=False))
        sys.exit(1)

    text = path.read_text(encoding="utf-8")

    try:
        tool = copy_text(text)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Clipboard copy failed: {exc}"},
                         ensure_ascii=False))
        sys.exit(1)

    print(json.dumps({
        "ok": True,
        "copied_from": str(path),
        "chars": len(text),
        "via": tool,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
