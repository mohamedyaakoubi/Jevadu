"""Serve the website on this computer only.

python -m hackathon_memory.web              http://127.0.0.1:8000
python -m hackathon_memory.web --port 8080
python -m hackathon_memory.web --rehearsal  registrations go to the rehearsal topic, and every
                                            page says so (design 9.3)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def main(argv: Sequence[str]) -> int:
    import uvicorn

    from hackathon_memory.settings import Settings
    from hackathon_memory.web.app import create_app

    parser = argparse.ArgumentParser(prog="python -m hackathon_memory.web")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--rehearsal", action="store_true")
    arguments = parser.parse_args(argv)
    settings = Settings()
    if arguments.rehearsal:
        topic = settings.hedera_rehearsal_topic_id.strip()
        if not topic:
            print("HEDERA_REHEARSAL_TOPIC_ID is empty in .env. Open the rehearsal topic first: "
                  "python -m hackathon_memory.hedera.registry open --rehearsal")  # fmt: skip
            return 2
        settings = settings.model_copy(update={"hedera_topic_id": topic})
        print(f"Rehearsal: registrations go to the topic {topic}, not to the register.")
    print(f"Open http://127.0.0.1:{arguments.port} in your browser. Stop with Ctrl+C.")
    # 127.0.0.1 only: the website is not reachable from other computers (nothing is put online).
    # An idea travels in the address of the page: 64 KB hold the longest idea in any script
    # (app.LONGEST_IDEA); the default of h11 is 16 KB.
    app = create_app(settings, rehearsal=arguments.rehearsal)
    uvicorn.run(app, host="127.0.0.1", port=arguments.port, log_level="warning",
                h11_max_incomplete_event_size=64 * 1024)  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
