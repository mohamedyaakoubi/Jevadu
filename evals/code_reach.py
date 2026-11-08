"""What the rule of the files that nothing uses changes (parse/hedera_code.py, format 4, 8
November 2026).

A random sample of the repositories of the collection whose saved reading names a Hedera service
is read again with the new reader, into a scratch folder: nothing of the collection changes. For
each one, the services that the old reading counted as called are set beside those that the new
one counts, and the services found only in files that nothing uses are listed with those files.
The result file says how many repositories lose a service, and which.

    python -m evals.code_reach [--sample 80] [--seed 8]

GitHub is asked as the pipeline asks it (collect/github.py): one request at a time, with the
tool's name and contact address, counted on disk. Each repository takes two requests.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from hackathon_memory.collect import github
from hackathon_memory.collect.answers import Answers
from hackathon_memory.collect.github_code import fetch_code, saved_code
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.settings import Settings

RESULTS = Path(__file__).parent / "results"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.code_reach")
    parser.add_argument("--sample", type=int, default=80)
    parser.add_argument("--seed", type=int, default=8)
    arguments = parser.parse_args(argv)
    settings = Settings()
    answers = Answers(github.raw_dir(settings))
    with psycopg.connect(settings.database_conninfo(), connect_timeout=5) as conn:
        repositories = [row[0] for row in conn.execute(
            "SELECT url FROM repositories WHERE archive_status = 'read' ORDER BY url")]  # fmt: skip
    calling = []
    for url in repositories:
        read = saved_code(answers, url)
        if read is not None and read.scan is not None and read.scan.features:
            calling.append((url, read.scan))
    draw = random.Random(arguments.seed)  # noqa: S311 - a sample to measure, not a secret
    sample = draw.sample(calling, min(arguments.sample, len(calling)))
    client = github.github_client(settings)
    collector = f"{settings.collector_name.strip()}/code-reach"
    rows, failed = [], []
    with tempfile.TemporaryDirectory() as scratch:
        store = RawStore(Path(scratch) / "raw")
        for number, (url, old) in enumerate(sample, 1):
            fetch_code(client, store, [url], collector=collector)
            new = saved_code(store, url)
            if new is None or new.scan is None or new.scan.partial:
                failed.append(url)
                continue
            before, after = sorted(old.features), sorted(new.scan.features)
            rows.append({
                "repository": url, "before": before, "after": after,
                "lost": sorted(set(before) - set(after)),
                "unused_only": {name: one.examples for name, one in new.scan.unused_only.items()},
                "unused_files": sorted({path for one in new.scan.unused.values()
                                        for path in one.examples}),
                "commit_before": old.commit, "commit_after": new.scan.commit,
            })  # fmt: skip
            print(f"{number}/{len(sample)} {url}: lost {rows[-1]['lost'] or 'nothing'}", flush=True)
    changed = [row for row in rows if row["lost"]]
    same_commit = [row for row in rows if row["commit_before"] == row["commit_after"]]
    result = {
        "made_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "what": "services counted as called by the code, before and after the rule of the files "
                "that nothing uses (parse/hedera_code.py, format 4)",
        "repositories_with_a_service": len(calling), "sample": len(sample), "seed": arguments.seed,
        "read_again": len(rows), "not_read": failed,
        "lose_a_service": len(changed),
        "lose_a_service_same_commit": len([row for row in changed if row in same_commit]),
        "keep_every_service": len(rows) - len(changed),
        "services_lost": sorted({name for row in changed for name in row["lost"]}),
        "rows": rows,
    }  # fmt: skip
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"{stamp}-code-reach.json"
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"read again {len(rows)} of {len(sample)}; {len(changed)} lose a service; written {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
