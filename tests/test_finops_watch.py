"""The watch over the public copy's spending (finops/watch.py): where its budget stands, what its
visitors used, and a failed job once a share of a cap is spent. Everything is invented."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg

from hackathon_memory.db.migrate import migrate
from hackathon_memory.finops import watch
from hackathon_memory.settings import Settings

NOW = datetime(2026, 10, 30, 15, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


def called(database: str, cost: float | None, at: datetime, purpose: str = "rerank",
           environment: str = "public", ok: bool = True) -> None:  # fmt: skip
    with psycopg.connect(database) as conn:
        conn.execute(
            "INSERT INTO llm_calls (called_at, environment, purpose, model, input_tokens, ok, "
            "cost_usd) VALUES (%s, %s, %s, 'gemini-3.8-flash', 100, %s, %s)",
            (at, environment, purpose, ok, cost),
        )


def test_the_watch_says_where_the_public_budget_stands(empty_database: str) -> None:
    migrate(empty_database)
    called(empty_database, 0.5, datetime(2026, 10, 29, 23, 0, tzinfo=UTC))  # yesterday, in UTC
    called(empty_database, 0.25, datetime(2026, 10, 30, 1, 0, tzinfo=UTC), "compare")
    called(empty_database, 0.0, datetime(2026, 10, 30, 2, 0, tzinfo=UTC), ok=False)
    called(empty_database, None, datetime(2026, 10, 30, 3, 0, tzinfo=UTC), "embed_query")
    called(empty_database, 9.0, datetime(2026, 10, 30, 4, 0, tzinfo=UTC), environment="test")
    with psycopg.connect(empty_database) as conn:
        conn.execute(
            "INSERT INTO visitor_uses (scope, client, kind, count) VALUES "
            "('visitor', %s, 'ai', 3), ('visitor', %s, 'ai', 1), ('address', %s, 'ai', 4)",
            ("a" * 64, "b" * 64, "c" * 64),
        )
        conn.execute("INSERT INTO site_switches (name, turned_on) VALUES ('ai', true), "
                     "('register', false)")  # fmt: skip
    found = watch.standing(empty_database, NOW)
    assert (found.spent_usd, found.spent_today_usd) == (0.75, 0.25)  # not the test environment
    assert (found.calls, found.calls_today, found.failed_today, found.unpriced) == (4, 3, 1, 1)
    assert found.used == (("ai", 2, 4),)  # the share of an address is not a visitor
    assert found.switches == (("ai", True), ("register", False))
    assert watch.alerts(found, 30, 5) == []
    text = watch.report(found, 30, 5, [])
    assert "- No cap is near." in text
    assert "- Spent: $0.7500 of $30.00, in 4 calls to a model." in text
    assert "- Today (UTC): $0.2500 of $5.00, in 3 calls, 1 of them failed." in text
    assert "- Last call: 30 October 2026, 03:00 UTC." in text
    assert "Calls with no known price: 1." in text
    assert "| asks of Gemini | 2 | 4 |" in text and "- Switches: ai on, register off." in text
    assert "| rerank | 2 | 0.5000 |" in text


def test_the_watch_fails_once_a_share_of_a_cap_is_spent(empty_database: str,
                                                         tmp_path: Path) -> None:  # fmt: skip
    migrate(empty_database)
    now = datetime.now(UTC)
    called(empty_database, 4.0, now)
    summary = tmp_path / "summary.md"
    kept = {watch.DATABASE: empty_database, "GITHUB_STEP_SUMMARY": str(summary)}
    assert watch.main(kept) == 1  # $4 of today's $5: 80%
    assert "80% of today's budget is spent ($4.00 of $5.00, the day in UTC)." in summary.read_text(
        encoding="utf-8"
    )
    assert watch.main({**kept, "LLM_BUDGET_PUBLIC_PER_DAY_USD": "10"}) == 0  # the job's own caps
    called(empty_database, 20.0, now - timedelta(days=3))
    assert watch.main({**kept, "LLM_BUDGET_PUBLIC_PER_DAY_USD": "10"}) == 1  # $24 of $30
    assert "80% of the whole budget is spent ($24.00 of $30.00)." in summary.read_text(
        encoding="utf-8"
    )


def test_the_watch_says_when_it_cannot_read(capsys) -> None:  # noqa: ANN001
    assert watch.main({}) == 2
    assert watch.main({watch.DATABASE: "not a connection text"}) == 2
    said = capsys.readouterr().out
    assert "PUBLIC_COSTS_DATABASE_URL is not set" in said
    assert "could not be read (ProgrammingError)" in said and "not a connection" not in said


def test_the_watch_reads_the_dotenv_of_a_laptop(empty_database: str, tmp_path: Path,
                                                 monkeypatch, capsys) -> None:  # noqa: ANN001  # fmt: skip
    """The README tells to keep the setting in .env, and the command printed "not set" on a
    laptop, where only the job gives it in the environment (31 October 2026)."""
    migrate(empty_database)
    called(empty_database, 4.0, datetime.now(UTC))
    lines = ["# the database of the public copy", f'PUBLIC_COSTS_DATABASE_URL="{empty_database}"',
             "LLM_BUDGET_PUBLIC_PER_DAY_USD=10", "OTHER=x=y"]  # fmt: skip
    (tmp_path / ".env").write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    for name in watch.GIVEN:
        monkeypatch.delenv(name, raising=False)
    assert watch.main() == 0  # $4 of the .env's $10 a day; the default $5 would have warned
    assert "- Today (UTC): $4.0000 of $10.00" in capsys.readouterr().out
    monkeypatch.setenv("LLM_BUDGET_PUBLIC_PER_DAY_USD", "5")
    assert watch.main() == 1  # the environment wins over .env, as for the settings
    assert watch.from_dotenv(tmp_path / ".env", ["OTHER"]) == {"OTHER": "x=y"}
    assert watch.from_dotenv(tmp_path / "none", watch.GIVEN) == {}
    assert watch.main({}) == 2  # a run of the tests gives its own settings, and no .env is read


def test_the_watch_knows_the_caps_of_the_settings_and_needs_only_psycopg() -> None:
    """The job gives no caps, so the watch's are the settings' own; and it installs psycopg
    alone, so the module may import nothing else."""
    from hackathon_memory.web import public

    settings = Settings(_env_file=None)
    assert (watch.TOTAL_USD, watch.PER_DAY_USD) == (
        settings.llm_budget_public_usd, settings.llm_budget_public_per_day_usd)  # fmt: skip
    assert watch.SWITCHES == public.SWITCHES
    unset = watch.Standing(0, 0, 0, 0, 0, 0, None, (), (), ())
    assert "- Switches: ai off, register off." in watch.report(unset, 30, 5, [])
    tree = ast.parse((ROOT / "src/hackathon_memory/finops/watch.py").read_text(encoding="utf-8"))
    imported = {node.module.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module}  # fmt: skip
    imported |= {alias.name.split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.Import) for alias in node.names}  # fmt: skip
    assert imported <= {"__future__", "os", "sys", "collections", "dataclasses", "datetime",
                        "pathlib", "psycopg"}, imported  # fmt: skip
    workflow = (ROOT / ".github/workflows/costs.yml").read_text(encoding="utf-8")
    assert "python -m hackathon_memory.finops.watch" in workflow
    given = [line for line in workflow.splitlines()
             if "LLM_BUDGET_PUBLIC" in line and not line.lstrip().startswith("#")]  # fmt: skip
    assert given == []  # the job gives no caps of its own: those of the settings, as above
