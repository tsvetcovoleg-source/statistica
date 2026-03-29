#!/usr/bin/env python3
"""Open Safari on macOS, load Colab URL, and dump current page HTML.

This helper intentionally does ONLY two things:
1) Opens Safari in a new window with the target URL.
2) Reads page HTML (document.documentElement.outerHTML) and saves it to file.
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


TARGET_URL = "https://colab.research.google.com/drive/15i-UxCR47BFiehVg-2Z6tUQCyyG_iXel"
WAIT_BEFORE_DUMP_SECONDS = 8
OUTPUT_FILE = Path.home() / "Downloads" / "colab_page_source.html"


def log(message: str) -> None:
    """Print timestamped logs to terminal."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def run_osascript(script: str, stage: str) -> subprocess.CompletedProcess[str]:
    """Run AppleScript and return process result."""
    log(f"{stage}: running osascript")
    proc = subprocess.run(
        ["osascript", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )
    if proc.stdout.strip():
        log(f"{stage}: stdout -> {proc.stdout.strip()[:200]}...")
    if proc.stderr.strip():
        log(f"{stage}: stderr -> {proc.stderr.strip()}")
    log(f"{stage}: done")
    return proc


def open_colab_in_new_window() -> None:
    """Activate Safari and open target URL in a dedicated new window."""
    applescript = f'''
    tell application "Safari"
        activate
        set newDoc to make new document
        set URL of newDoc to "{TARGET_URL}"
    end tell
    '''
    run_osascript(applescript, stage="open_colab_in_new_window")


def get_front_page_info() -> str:
    """Return front page title and URL for debugging."""
    applescript = '''
    tell application "Safari"
        if not (exists front document) then return "no_document"
        set docTitle to (name of front document)
        set docURL to (URL of front document)
        return "title=" & docTitle & " | url=" & docURL
    end tell
    '''
    return run_osascript(applescript, stage="get_front_page_info").stdout.strip()


def get_front_page_html() -> str:
    """Get current front document HTML via JavaScript in Safari."""
    applescript = '''
    tell application "Safari"
        if not (exists front document) then return ""
        return (do JavaScript "document.documentElement.outerHTML" in front document)
    end tell
    '''
    return run_osascript(applescript, stage="get_front_page_html").stdout


def main() -> int:
    log("Script started")
    try:
        open_colab_in_new_window()

        log(f"Waiting {WAIT_BEFORE_DUMP_SECONDS}s for page to load")
        time.sleep(WAIT_BEFORE_DUMP_SECONDS)

        page_info = get_front_page_info()
        log(f"Front page: {page_info}")

        html = get_front_page_html()
        if not html.strip():
            log("HTML is empty")
            print("Failed to get page HTML (empty output).", file=sys.stderr)
            return 2

        OUTPUT_FILE.write_text(html, encoding="utf-8")
        log(f"Saved page source to: {OUTPUT_FILE}")
        print(f"OK. HTML saved to: {OUTPUT_FILE}")
        return 0

    except FileNotFoundError:
        print("Error: 'osascript' not found. This script must be run on macOS.", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"AppleScript error: {exc}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
