"""Gate A, proof 4: PostgreSQL with pgvector runs in Docker and answers a vector query.

Design section 14.2. Run it from the project folder:  python -m proofs.database

It also tests two claims of design section 11.6 on the real server, because a claim that
nobody tested is only a guess:

* the normal index of pgvector stops at 2,000 numbers, and our embeddings have 3,072;
* the half-size type gives an index that works for 3,072 numbers.

The vectors are random numbers made here. No project data is used.
"""

from __future__ import annotations

import math
import random
import statistics
import sys
import time

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg import sql

from hackathon_memory.db.migrate import migrate, status
from hackathon_memory.settings import Settings, SettingsError
from proofs.result import ProofResult

DIMENSIONS = 3072  # the size of a gemini-embedding-001 answer
ROWS = 3000  # about the number of projects the tool will hold (design section 11.6)
SEED = 20261009  # a fixed seed, so every run plants the same vectors
QUERIES_TIMED = 20

N = sql.Literal(DIMENSIONS)  # the vector size, put into the statements below as a number

CREATE_TABLE = sql.SQL(
    "CREATE TEMP TABLE proof_vectors (id integer PRIMARY KEY, embedding vector({}))"
)
NEAREST = sql.SQL(
    "SELECT id, embedding <=> %s AS distance FROM proof_vectors ORDER BY embedding <=> %s LIMIT 10"
)
NORMAL_INDEX = sql.SQL(
    "CREATE INDEX proof_hnsw ON proof_vectors USING hnsw (embedding vector_cosine_ops)"
)
HALF_INDEX = sql.SQL(
    "CREATE INDEX proof_hnsw_half ON proof_vectors USING hnsw "
    "((embedding::halfvec({})) halfvec_cosine_ops)"
)
HALF_PLAN = sql.SQL(
    "EXPLAIN SELECT id FROM proof_vectors "
    "ORDER BY embedding::halfvec({n}) <=> %s::halfvec({n}) LIMIT 10"
)


def unit_vector(rng: random.Random) -> list[float]:
    values = [rng.gauss(0.0, 1.0) for _ in range(DIMENSIONS)]
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


def near(rng: random.Random, base: list[float], noise: float) -> list[float]:
    """A unit vector close to `base`. A bigger `noise` means a farther vector."""
    values = [b + noise * rng.gauss(0.0, 1.0) / math.sqrt(DIMENSIONS) for b in base]
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


def cosine_distance(a: list[float], b: list[float]) -> float:
    """The number that the pgvector operator <=> gives, computed here without the database."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return 1.0 - dot / (norm_a * norm_b)


def run() -> int:
    result = ProofResult(proof="database")
    result.does_not_prove = [
        "It uses random vectors, not real embeddings. How well real embeddings find similar "
        "projects is measured by Test 2 (design 13.3), not here.",
        "The timings are from one laptop with 3,000 rows. They are not a promise for a server.",
        "It does not test the data model. The tables of design section 10 come in Phase B.",
    ]
    try:
        settings = Settings()
        conninfo = settings.database_conninfo()
        result.hide(conninfo, settings.postgres_password.get_secret_value())
        migrate(conninfo)
        states = status(conninfo)
    except SettingsError as error:
        result.check("settings are complete", False, str(error))
        return result.finish()
    except psycopg.OperationalError:
        result.check("database is reachable", False, "run: docker compose up -d --wait db")
        return result.finish()

    result.check(
        "migrations are applied", all(s.applied for s in states), f"{len(states)} migration(s)"
    )

    with psycopg.connect(conninfo, autocommit=True) as conn:
        register_vector(conn)
        server = conn.execute("SHOW server_version").fetchone()[0]
        extension = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        result.measurements["server_version"] = server
        result.measurements["pgvector_version"] = extension[0] if extension else None
        result.check(
            "the vector add-on is on",
            extension is not None,
            f"pgvector {extension[0]}" if extension else "",
        )

        # --- plant a known answer among random rows
        rng = random.Random(SEED)  # noqa: S311 (a fixed seed on purpose: nothing here is secret)
        query = unit_vector(rng)
        planted = [
            (1, near(rng, query, 0.4)),
            (2, near(rng, query, 1.2)),
            (3, near(rng, query, 2.4)),
        ]
        rows = planted + [(i, unit_vector(rng)) for i in range(4, ROWS + 1)]

        conn.execute(CREATE_TABLE.format(N))
        started = time.perf_counter()
        copy_sql = "COPY proof_vectors (id, embedding) FROM STDIN (FORMAT BINARY)"
        with conn.cursor() as cur, cur.copy(copy_sql) as copy:
            copy.set_types(["int4", "vector"])
            for row_id, values in rows:
                copy.write_row((row_id, Vector(values)))
        result.measurements["insert_seconds"] = round(time.perf_counter() - started, 2)
        count = conn.execute("SELECT count(*) FROM proof_vectors").fetchone()[0]
        result.check("3,072-number vectors can be stored", count == ROWS, f"{count} rows")

        # --- the answer is right
        top = conn.execute(NEAREST, (Vector(query), Vector(query))).fetchall()
        first_three = [r[0] for r in top[:3]]
        result.check(
            "the planted neighbours come first, nearest first",
            first_three == [1, 2, 3],
            f"top 3 ids: {first_three}",
        )
        by_id = dict(rows)
        worst = max(abs(d - cosine_distance(query, by_id[row_id])) for row_id, d in top)
        result.check(
            "the database distance equals an independent computation",
            worst < 1e-4,
            f"largest difference {worst:.2e} over the top 10",
        )
        result.measurements["distance_difference_max"] = worst

        # --- exact search is fast enough at our size, with no index
        timings = []
        for _ in range(QUERIES_TIMED):
            started = time.perf_counter()
            conn.execute(NEAREST, (Vector(query), Vector(query))).fetchall()
            timings.append((time.perf_counter() - started) * 1000)
        median_ms = statistics.median(timings)
        result.measurements["exact_search_ms_median"] = round(median_ms, 1)
        result.measurements["exact_search_ms_max"] = round(max(timings), 1)
        result.check(
            "an exact search over 3,000 rows needs no index",
            median_ms < 500,
            f"median {median_ms:.0f} ms, slowest {max(timings):.0f} ms, {QUERIES_TIMED} runs",
        )

        # --- claim 1 of design 11.6: the normal index stops at 2,000 numbers
        try:
            conn.execute(NORMAL_INDEX)
            result.check("the normal index refuses 3,072 numbers", False, "the index was created")
        except psycopg.Error as error:
            message = str(error).strip().splitlines()[0]
            result.check("the normal index refuses 3,072 numbers", "2000" in message, message)

        # --- claim 2: the half-size type gives a working index
        try:
            conn.execute(HALF_INDEX.format(N))
            conn.execute("SET enable_seqscan = off")  # the planner must prefer the index
            plan_rows = conn.execute(HALF_PLAN.format(n=N), (Vector(query),)).fetchall()
            uses_index = "proof_hnsw_half" in "\n".join(row[0] for row in plan_rows)
            result.check("an index on the half-size type works and is used", uses_index)
        except psycopg.Error as error:
            first_line = str(error).strip().splitlines()[0]
            result.check("an index on the half-size type works and is used", False, first_line)

    return result.finish()


if __name__ == "__main__":
    sys.exit(run())
