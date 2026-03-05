#!/usr/bin/env python3
"""SessionStart / UserPromptSubmit hook: Inject current timestamp.

Prints a time sync message that Claude Code can use for date-aware operations.
Runs on every session start and before every user prompt submission.
"""

import sys
from datetime import datetime

def main() -> None:
    now = datetime.now()
    formatted = now.strftime("%Y-%m-%d %H:%M:%S %A")
    tz = datetime.now().astimezone().tzname()
    print(f"[TIME SYNC] {formatted} | TZ: {tz}")
    sys.exit(0)

if __name__ == "__main__":
    main()
