"""The result file of a proof must be useful, honest, and free of secrets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proofs import result as result_module
from proofs.result import ProofResult

SECRET = "CANARY-do-not-print-0123456789"


@pytest.fixture
def results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "proofs" / "results"
    monkeypatch.setattr(result_module, "RESULTS_DIR", folder)
    return folder


def test_a_secret_is_removed_from_the_printed_line_and_from_the_file(
    results_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proof = ProofResult(proof="demo")
    proof.hide(SECRET)
    proof.check(f"connect with {SECRET}", True, detail=f"password {SECRET} was refused")
    proof.measurements["note"] = f"text with {SECRET}"
    saved = proof.save()

    assert SECRET not in capsys.readouterr().out
    assert SECRET not in saved.read_text(encoding="utf-8")


def test_a_proof_with_no_check_does_not_pass(results_dir: Path) -> None:
    assert ProofResult(proof="demo").passed is False


def test_one_failed_check_fails_the_proof(results_dir: Path) -> None:
    proof = ProofResult(proof="demo")
    proof.check("first", True)
    proof.check("second", False, "it broke")
    assert proof.passed is False
    assert proof.finish() == 1


def test_the_file_holds_what_a_reader_needs(results_dir: Path) -> None:
    proof = ProofResult(proof="demo")
    proof.check("works", True, "detail")
    proof.measurements["milliseconds"] = 12
    proof.does_not_prove = ["it does not prove the moon is made of cheese"]
    body = json.loads(proof.save().read_text(encoding="utf-8"))

    assert body["proof"] == "demo"
    assert body["gate"] == "A"
    assert body["passed"] is True
    assert body["checks"] == [{"name": "works", "passed": True, "detail": "detail"}]
    assert body["measurements"] == {"milliseconds": 12}
    assert body["does_not_prove"]
    assert body["ran_at"].endswith("Z")


def test_the_file_name_works_on_windows(results_dir: Path) -> None:
    name = ProofResult(proof="demo").save().name
    assert ":" not in name
    assert name.endswith("-demo.json")
