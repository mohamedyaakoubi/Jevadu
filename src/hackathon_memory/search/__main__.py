"""Command line for the search: a plain listing, for now (design 14.3).

    python -m hackathon_memory.search "a wallet that pays street vendors in tokens"
    python -m hackathon_memory.search "..." --limit 20
    python -m hackathon_memory.search "..." --numbers-only

The idea is embedded once a day at most, through the meter and its budget. It is kept nowhere:
only its fingerprint goes with its embedding, for one day. `--numbers-only` shows the places,
states and counts, and no name, link or id of a project.
"""

from __future__ import annotations

import argparse
import sys

import psycopg

from hackathon_memory.db.embeddings import EmbeddingStore
from hackathon_memory.finops.budget import BudgetExceeded
from hackathon_memory.finops.meter import metered_client
from hackathon_memory.search import engine, listing
from hackathon_memory.settings import Settings, SettingsError

USAGE = 'usage: python -m hackathon_memory.search "<an idea>" [--limit N] [--numbers-only]'


class _Quiet(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse would exit; the caller prints the usage
        raise ValueError(message)


def main(argv: list[str], settings: Settings | None = None, client: object = None) -> int:
    parser = _Quiet(prog="python -m hackathon_memory.search", add_help=False)
    parser.add_argument("idea")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--numbers-only", action="store_true")
    try:
        arguments = parser.parse_args(argv)
        if not arguments.idea.strip() or not 1 <= arguments.limit <= 50:
            raise ValueError("an idea, and a limit from 1 to 50")
    except ValueError:
        print(USAGE)
        return 2
    settings = settings or Settings()
    model = settings.gemini_embedding_model
    try:
        conninfo = settings.database_conninfo()
        google = client or metered_client(settings, "embed_query")
        if not EmbeddingStore(conninfo).counts(model)["embeddings"]:
            print(
                "No project has an embedding yet, so only the words were searched. "
                "(python -m hackathon_memory.pipeline embed)"
            )
        hits = engine.search(
            conninfo,
            google,
            arguments.idea,
            model=model,
            limit=arguments.limit,
        )
        found = listing.cards(conninfo, hits)
    except SettingsError as problem:
        print(f"Stopped: {problem}")
        return 1
    except BudgetExceeded as over:
        print(f"Stopped: {over}")
        return 1
    except psycopg.OperationalError:
        # The message of this error can hold the connection text, so it is not shown.
        print("Stopped: cannot reach the database. Is it running? (docker compose up -d db)")
        return 1
    if not found:
        print("No project was found.")
        return 0
    print("\n".join(listing.lines(found, names=not arguments.numbers_only)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
