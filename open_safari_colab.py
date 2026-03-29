#!/usr/bin/env python3
"""Open Safari on macOS and navigate to a specific URL.

This script:
1) Launches Safari if it is not running.
2) Brings Safari to the foreground if it is already running.
3) Opens a NEW Safari window and navigates it to the target Google Colab URL.

Note: On first run, macOS may ask for Automation / Apple Events permission.
"""

import subprocess
import sys


TARGET_URL = "https://colab.research.google.com/drive/15i-UxCR47BFiehVg-2Z6tUQCyyG_iXel"


def main() -> int:
    # AppleScript is the most reliable native way to control Safari on macOS.
    applescript = f'''
    tell application "Safari"
        activate
        -- Create a separate new window so current browsing work is not disturbed.
        set newDoc to make new document
        set URL of newDoc to "{TARGET_URL}"
    end tell
    '''

    try:
        # Run AppleScript via osascript. If Safari is closed, it will launch it.
        # If Safari is already open, it will move it to the foreground and use a new window.
        subprocess.run(["osascript", "-e", applescript], check=True)
        print("Safari activated and URL opened successfully.")
        return 0
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
