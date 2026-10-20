"""Enter the 429 of 11 October 2026, 00:00:11 UTC, into the count of requests. Run once.

The site answered "too many requests" before the tool knew how to remember that. This script
writes the event into data/requests/ethglobal.com.json through the tool's own code, with the
real time of the answer and the pause that was in use (2 seconds). From then on every command
keeps to the cooldown (one hour) and to the slower pace (10 seconds) by itself.

It sends no request. It refuses to run twice.
"""

import sys
from datetime import UTC, datetime

from hackathon_memory.collect.ethglobal import data_paths, request_count
from hackathon_memory.settings import Settings

count = request_count(data_paths(Settings()))
if count.min_pause() > 0 or count.not_before() is not None:
    print("already entered, nothing done")
    sys.exit(1)
goes_on = count.note_too_many(None, 2.0, at=datetime(2026, 10, 11, 0, 0, 11, tzinfo=UTC))
print(f"entered. goes on by itself: {goes_on}")
print(f"no request before: {count.not_before():%Y-%m-%d %H:%M:%S} UTC ({count.wait_left() / 60:.0f} minutes from now)")
print(f"pause from then on: {count.min_pause():.0f} seconds")
