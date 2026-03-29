#!/usr/bin/env python3
"""Open Safari on macOS, navigate to Colab, and press Run all.

This script:
1) Launches Safari if it is not running.
2) Brings Safari to the foreground if it is already running.
3) Opens a NEW Safari window and navigates it to the target Google Colab URL.
4) Waits for page load and tries to click the "Run all" button automatically.

Note: On first run, macOS may ask for Automation / Apple Events permission.
"""

from __future__ import annotations

import subprocess
import sys
import time


TARGET_URL = "https://colab.research.google.com/drive/15i-UxCR47BFiehVg-2Z6tUQCyyG_iXel"
WAIT_TIMEOUT_SECONDS = 60
POLL_INTERVAL_SECONDS = 1.5


def run_osascript(script: str) -> subprocess.CompletedProcess[str]:
    """Execute AppleScript and return the completed process."""
    return subprocess.run(
        ["osascript", "-e", script],
        check=True,
        text=True,
        capture_output=True,
    )


def open_colab_in_new_window() -> None:
    """Activate Safari and open URL in a dedicated new window."""
    applescript = f'''
    tell application "Safari"
        activate
        -- Create a separate new window so current browsing work is not disturbed.
        set newDoc to make new document
        set URL of newDoc to "{TARGET_URL}"
    end tell
    '''
    run_osascript(applescript)


def try_click_run_all() -> bool:
    """Try to click 'Run all' button in the active Safari tab via JavaScript."""
    js = r'''(() => {
      const targets = [
        'Run all',
        'Выполнить все',
        'Запустить все'
      ].map(t => t.toLowerCase());

      const isVisible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
      };

      const clickIfMatch = (el) => {
        const text = (el.innerText || el.textContent || '').trim().toLowerCase();
        if (!text) return false;
        if (!targets.some(t => text === t || text.includes(t))) return false;
        if (!isVisible(el)) return false;
        el.click();
        return true;
      };

      const candidates = Array.from(document.querySelectorAll('button,[role="button"],div,span,a'));
      for (const el of candidates) {
        if (clickIfMatch(el)) return 'clicked';
      }

      return document.readyState === 'complete' ? 'ready_but_not_found' : 'loading';
    })();'''

    applescript = f'''
    tell application "Safari"
        if not (exists front document) then return "no_document"
        return (do JavaScript {js!r} in front document)
    end tell
    '''

    result = run_osascript(applescript).stdout.strip()
    return result == "clicked"


def wait_and_click_run_all(timeout_seconds: int = WAIT_TIMEOUT_SECONDS) -> bool:
    """Poll page for 'Run all' and click it when available."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if try_click_run_all():
                return True
        except subprocess.CalledProcessError:
            # Page may still be loading; retry until timeout.
            pass
        time.sleep(POLL_INTERVAL_SECONDS)
    return False


def main() -> int:
    try:
        open_colab_in_new_window()
        clicked = wait_and_click_run_all()

        if clicked:
            print("Safari activated, URL opened, and 'Run all' clicked.")
            return 0

        print(
            "Safari activated and URL opened, but 'Run all' was not found within timeout. "
            "Open page manually and click it once if needed.",
            file=sys.stderr,
        )
        return 2

    except FileNotFoundError:
        # osascript exists only on macOS; this makes the failure reason explicit.
        print("Error: 'osascript' not found. This script must be run on macOS.", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        # Typical reason: macOS Automation permission denied by user/system policy.
        print(f"Failed to control Safari via AppleScript: {exc}", file=sys.stderr)
        print(
            "If prompted, allow Terminal (or your Python app) to control Safari in "
            "System Settings -> Privacy & Security -> Automation.",
            file=sys.stderr,
        )
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
