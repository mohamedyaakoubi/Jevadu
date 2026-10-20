"""Write the count of requests to ethglobal.com as it stands before the first counted command.

24 requests were sent on 10 October 2026 by throw-away scripts and by the look, before the count
existed: 19 for the investigation of the site (entry 07 of the notes) and 5 for the Hedera list
(pages 1, 2, 3, 3 and 1). They belong to the same promise of 300, so they are entered here once.
The script refuses to run when the file already exists.
"""

import json
import sys
from pathlib import Path

path = Path.cwd() / "data" / "requests" / "ethglobal.com.json"
if path.exists():
    print(f"already there, not touched: {path}")
    sys.exit(1)
record = {
    "site": "ethglobal.com",
    "sent": 24,
    "by_day": {"2026-10-10": 24},
    "notes": [
        "24 requests were sent on 10 October 2026 before this count existed: 19 for the "
        "investigation of the site and the look, and 5 for the first pages of the Hedera list. "
        "Entered by hand, once."
    ],
}
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
print(f"written: {path} (sent = {record['sent']})")
