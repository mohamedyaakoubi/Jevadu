"""The Google proof script, run against the real library with a fake network.

This tests the proof's own logic and what it writes to its result file. It cannot show that the
real service answers the same way: that is what the live run is for.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from googlefake import FakeGoogle, answer
from hackathon_memory.settings import Settings
from proofs import google_models
from proofs import result as result_module
from proofs.google_models import RealText

PROJECT = "secret-project-id-123"
PAGE = "PAGE-CANARY-TEXT lets a shop keep a public list of small facts on Hedera."
REAL = RealText(name="Zed Widget", text=PAGE)


def settings(**values: object) -> Settings:
    defaults = {"google_cloud_project": PROJECT, "google_cloud_location": "global"}
    return Settings(_env_file=None, **(defaults | values))  # type: ignore[arg-type]


def vectors(content: str) -> list[float]:
    """Texts about the project are close to each other. The cake question is far from them."""
    near = [1.0] + [0.0] * 3071
    far = [0.0, 1.0] + [0.0] * 3070
    return far if "chocolate" in content else near


@pytest.fixture
def results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "proofs" / "results"
    monkeypatch.setattr(result_module, "RESULTS_DIR", folder)
    return folder


def run_with(google: FakeGoogle, **options: object) -> int:
    return google_models.run(
        options.pop("settings", None) or settings(),  # type: ignore[arg-type]
        make=lambda _settings: google.client(),
        text_source=options.pop("text_source", lambda _s: REAL),  # type: ignore[arg-type]
    )


def saved(results_dir: Path) -> dict:
    files = list(results_dir.glob("*-google-models.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


def failed(body: dict) -> list[str]:
    return [c["name"] for c in body["checks"] if not c["passed"]]


def good_google() -> FakeGoogle:
    google = FakeGoogle(answer())
    google.vector_for = vectors
    return google


def test_everything_works(results_dir: Path) -> None:
    google = good_google()
    assert run_with(google) == 0
    body = saved(results_dir)
    assert body["passed"] is True
    measured = body["measurements"]
    assert measured["model"] == "gemini-3.8-flash"
    assert measured["location"] == "global"
    assert measured["embedding_dimensions"] == 3072
    assert measured["similarity_related"] > measured["similarity_unrelated"]
    assert measured["gemini_cost_usd"] == pytest.approx(0.002625)
    assert measured["labels"]["not_found"] == 2  # problem and solution
    assert measured["quotes_total"] > 0
    assert measured["text_words"] == len(PAGE.split())


def test_the_result_file_holds_no_text_and_no_project_name(results_dir: Path) -> None:
    run_with(good_google())
    text = next(results_dir.glob("*-google-models.json")).read_text(encoding="utf-8")
    assert "PAGE-CANARY-TEXT" not in text  # nothing of the page
    assert "Zed Widget lets" not in text  # nothing of the answer
    assert PROJECT not in text


def test_a_google_error_that_names_the_project_is_scrubbed(results_dir: Path) -> None:
    google = good_google()
    google.fail_with = (403, f"Permission denied on project {PROJECT} for this model")
    assert run_with(google) == 1
    body = saved(results_dir)
    assert "Gemini 3.8 Flash returned a valid form" in failed(body)
    text = json.dumps(body)
    assert PROJECT not in text
    assert "Permission denied" in text  # the reason itself stays


def test_an_invalid_form_fails_that_check_but_the_embeddings_still_run(
    results_dir: Path,
) -> None:
    google = FakeGoogle("not json at all")
    google.vector_for = vectors
    assert run_with(google) == 1
    body = saved(results_dir)
    assert failed(body) == ["Gemini 3.8 Flash returned a valid form"]
    assert body["measurements"]["embedding_dimensions"] == 3072


def test_a_vector_of_the_wrong_size_fails_the_proof(results_dir: Path) -> None:
    google = good_google()
    google.embedding_size = 768
    google.vector_for = None
    assert run_with(google) == 1
    assert "the embedding model returned vectors of the expected size" in failed(saved(results_dir))


def test_a_question_that_is_not_closer_fails_the_proof(results_dir: Path) -> None:
    google = good_google()
    google.vector_for = None  # every text gets the same vector: no difference to find
    assert run_with(google) == 1
    names = failed(saved(results_dir))
    assert "a question about the text is closer to it than an unrelated question" in names


def test_missing_setup_blocks_the_proof_and_writes_no_file(
    results_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    google = good_google()
    assert run_with(google, settings=settings(google_cloud_project="")) == 3
    assert "Blocked" in capsys.readouterr().out
    assert google.requests == []
    assert not results_dir.exists() or not list(results_dir.glob("*"))


def test_a_location_that_the_model_is_not_offered_in_is_reported(results_dir: Path) -> None:
    google = good_google()
    assert run_with(google, settings=settings(google_cloud_location="us-central1")) == 1
    assert "the location is one that Gemini 3.8 Flash is offered in" in failed(saved(results_dir))
    assert google.requests == []  # nothing was sent


def test_a_missing_real_text_is_reported(results_dir: Path) -> None:
    google = good_google()
    assert run_with(google, text_source=lambda _s: None) == 1
    assert google.requests == []


def test_the_real_text_is_the_longest_description(tmp_path: Path) -> None:
    folder = tmp_path / "by-hand" / "hol.org"
    folder.mkdir(parents=True)
    entries = [
        {"name": "Short", "description_as_published": "a b c"},
        {"name": "Long", "description_as_published": "a b c d e f g"},
    ]
    (folder / "hedera-x-ai-2025-winners.entries.json").write_text(
        json.dumps(entries), encoding="utf-8"
    )
    real = google_models.load_real_text(settings(data_dir=str(tmp_path)))
    assert real is not None
    assert real.name == "Long"
    assert google_models.load_real_text(settings(data_dir=str(tmp_path / "none"))) is None
