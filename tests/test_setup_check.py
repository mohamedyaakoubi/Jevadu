"""The setup check tells what is missing, and never shows a value."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hackathon_memory.settings import Settings
from hackathon_memory.setup_check import blockers, latest_result, render, report

ECDSA_DER = "3030020100300706052b8104000a04220420"
CANARY = "CANARY-value-must-not-print"


def settings(tmp_path: Path, **values: object) -> Settings:
    return Settings(_env_file=None, data_dir=str(tmp_path / "data"), **values)  # type: ignore[arg-type]


def lines_for(tmp_path: Path, **values: object):
    return report(
        settings(tmp_path, **values),
        root=tmp_path,
        env_file=tmp_path / ".env",
        probe=lambda _s: (True, "the local database answers"),
    )


def by_what(lines):
    return {line.what: line for line in lines}


def test_an_empty_setup_says_what_is_missing(tmp_path: Path) -> None:
    lines = by_what(lines_for(tmp_path))
    assert lines["the file .env"].ok is False
    assert lines["HEDERA_OPERATOR_ID"].ok is False
    assert lines["HEDERA_OPERATOR_KEY"].ok is False
    assert lines["GOOGLE_CLOUD_PROJECT"].ok is False
    assert lines["COLLECTOR_CONTACT_EMAIL"].ok is False
    assert lines["your list of ETHGlobal prize pages"].ok is False


def test_a_full_setup_is_all_ok(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("x", encoding="utf-8")
    prize = tmp_path / "data" / "by-hand" / "ethglobal.com"
    prize.mkdir(parents=True)
    (prize / "prize-pages.txt").write_text(
        "# checked\nhttps://ethglobal.com/events/e/prizes/hedera\n", encoding="utf-8"
    )
    lines = by_what(
        lines_for(
            tmp_path,
            hedera_operator_id="0.0.1234",
            hedera_operator_key=ECDSA_DER + os.urandom(32).hex(),
            github_token="token-value",
            google_cloud_project="a-project",
            google_cloud_location="global",
            collector_name="Tool-research",
            collector_contact_email="owner@example.test",
        )
    )
    for what in (
        "the file .env",
        "HEDERA_OPERATOR_ID",
        "HEDERA_OPERATOR_KEY",
        "GITHUB_TOKEN",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "COLLECTOR_NAME",
        "COLLECTOR_CONTACT_EMAIL",
        "your list of ETHGlobal prize pages",
    ):
        assert lines[what].ok, what
    assert lines["HEDERA_OPERATOR_KEY"].note == "set, a valid ECDSA key"
    assert lines["your list of ETHGlobal prize pages"].note == "1 address(es)"


def test_no_value_is_ever_printed(tmp_path: Path) -> None:
    key = ECDSA_DER + os.urandom(32).hex()
    text = render(
        lines_for(
            tmp_path,
            hedera_operator_id="0.0.1234",
            hedera_operator_key=key,
            github_token=CANARY,
            google_cloud_project=CANARY + "-project",
            collector_contact_email=CANARY + "@example.test",
            postgres_password=CANARY,
        )
    )
    assert CANARY not in text
    assert key not in text
    assert key[-64:] not in text


def test_a_broken_key_is_reported_without_showing_it(tmp_path: Path) -> None:
    lines = by_what(lines_for(tmp_path, hedera_operator_key=f"zz-{CANARY}"))
    assert lines["HEDERA_OPERATOR_KEY"].ok is False
    assert CANARY not in lines["HEDERA_OPERATOR_KEY"].note


def test_a_google_location_that_the_model_does_not_have_is_reported(tmp_path: Path) -> None:
    lines = by_what(lines_for(tmp_path, google_cloud_location="us-central1"))
    assert lines["GOOGLE_CLOUD_LOCATION"].ok is False
    assert "global" in lines["GOOGLE_CLOUD_LOCATION"].note


def test_the_main_network_is_flagged(tmp_path: Path) -> None:
    lines = by_what(lines_for(tmp_path, hedera_network="mainnet"))
    assert lines["HEDERA_NETWORK"].ok is False


def test_each_proof_names_what_blocks_it(tmp_path: Path) -> None:
    blocked = blockers(lines_for(tmp_path))
    assert blocked["Hedera write"] == ["HEDERA_OPERATOR_ID", "HEDERA_OPERATOR_KEY"]
    assert blocked["Google models"] == ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"]
    assert "COLLECTOR_CONTACT_EMAIL" in blocked["ETHGlobal live run"]
    assert blocked["database"] == []


def test_the_latest_result_file_of_a_proof_is_shown(tmp_path: Path) -> None:
    folder = tmp_path / "proofs" / "results"
    folder.mkdir(parents=True)
    assert latest_result(tmp_path, "database") == (False, "no result file yet")
    older = {"passed": False, "ran_at": "2026-10-09T10:00:00Z"}
    newer = {"passed": True, "ran_at": "2026-10-09T18:00:00Z"}
    (folder / "20261009T100000Z-database.json").write_text(json.dumps(older), encoding="utf-8")
    (folder / "20261009T180000Z-database.json").write_text(json.dumps(newer), encoding="utf-8")
    ok, note = latest_result(tmp_path, "database")
    assert ok is True
    assert "passed on 2026-10-09T18:00:00Z" in note


def test_the_report_reads_as_a_page(tmp_path: Path) -> None:
    text = render(lines_for(tmp_path))
    assert text.startswith("Setup check. No value of .env is printed.")
    assert "What blocks each proof of Gate A:" in text
    assert "TO DO" in text


def test_a_wrong_database_password_is_told_apart_from_a_stopped_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import psycopg

    from hackathon_memory import setup_check

    def refuse(*_a: object, **_k: object) -> None:
        raise psycopg.OperationalError(
            'connection failed: FATAL:  password authentication failed for user "hackathon"'
        )

    monkeypatch.setattr(setup_check.psycopg, "connect", refuse)
    ok, note = setup_check.probe_database(settings(tmp_path, postgres_password=CANARY))
    assert ok is False
    assert "refuses the password" in note
    assert "docker compose down -v" in note
    assert CANARY not in note

    def unreachable(*_a: object, **_k: object) -> None:
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(setup_check.psycopg, "connect", unreachable)
    ok, note = setup_check.probe_database(settings(tmp_path, postgres_password=CANARY))
    assert ok is False
    assert "start Docker Desktop" in note


def test_no_password_is_reported_before_any_connection(tmp_path: Path) -> None:
    from hackathon_memory.setup_check import probe_database

    ok, note = probe_database(settings(tmp_path))
    assert ok is False
    assert "POSTGRES_PASSWORD is empty" in note
