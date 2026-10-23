"""The measure of the Hedera IDs in the code of a repository (evals/ids_in_code.py), on invented
archives and invented IDs."""

from __future__ import annotations

import io
from datetime import UTC, datetime

from evals import ids_in_code
from evals.ids_in_code import Drawn, IdsInCode, kind_of_file, measure, scan_ids
from fakes import archive
from hackathon_memory.check.ledger import LedgerFacts
from hackathon_memory.check.proof import Window
from hackathon_memory.parse.hedera_code import LimitedStream


def test_a_file_is_counted_where_it_stands() -> None:
    assert kind_of_file(".env.example") == "example_settings"
    assert kind_of_file("src/__tests__/topic.ts") == "test"
    assert kind_of_file("src/topic.test.ts") == "test"
    assert kind_of_file("config/hedera.json") == "settings"
    assert kind_of_file("src/topic.ts") == "source"


def test_the_ids_of_an_archive_are_found_by_the_rules_of_the_page() -> None:
    files = {
        ".env.example": b"OPERATOR_ID=0.0.12345\nTOPIC_ID=0.0.4870201\n",  # a counting example
        "src/topic.ts": b'const topicId = "0.0.4870201"; // the audit topic\n',
        "package.json": b'{"version": "0.0.3"}',  # a version number, never an ID
        "node_modules/x/index.js": b'const token = "0.0.5551234";',  # other people's code
    }
    found = scan_ids(LimitedStream(io.BytesIO(archive(files)).read))
    assert found.files == 3  # node_modules is skipped
    assert found.ids == {"0.0.4870201": {"example_settings", "source"}}


ASKED = datetime(2026, 10, 23, tzinfo=UTC)
EVENT = Window(datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 15, tzinfo=UTC))


def made(entity: str, day: datetime, kind: str = "topic") -> dict[str, LedgerFacts]:
    """What an invented test network says about an ID made on `day`."""
    return {"testnet": LedgerFacts(entity, "testnet", ASKED, True, kind=kind, created_at=day)}


def test_the_numbers_count_new_ids_and_those_on_the_ledger() -> None:
    repositories = {"https://github.com/a/one": Drawn(frozenset({"0.0.4870201"}), (EVENT,)),
                    "https://github.com/a/two": Drawn(windows=(EVENT,)),
                    "https://github.com/a/gone": Drawn()}  # fmt: skip
    read = {
        "https://github.com/a/one": IdsInCode(5, {"0.0.4870201": {"source"},
                                                    "0.0.4870202": {"settings"}}),
        "https://github.com/a/two": IdsInCode(2, {"0.0.4870203": {"source"}}),
        "https://github.com/a/gone": None,
    }  # fmt: skip
    ledger = {"0.0.4870202": made("0.0.4870202", datetime(2026, 9, 20, tzinfo=UTC)),
              "0.0.4870203": {}}  # fmt: skip
    numbers = measure(repositories, read, {"0.0.4870202"}, ledger)
    assert numbers["repositories_read"] == 2 and numbers["archives_not_read"] == 1
    assert numbers["repositories_with_a_new_id_in_code"] == 2
    assert numbers["repositories_with_a_new_id_on_the_ledger"] == 1
    assert numbers["repositories_with_a_new_own_id_on_the_ledger"] == 0  # named elsewhere
    assert numbers["repositories_with_a_new_id_made_in_the_window"] == 0  # so it is not weighed
    assert numbers["new_ids_in_code"] == 2 and numbers["new_ids_on_the_ledger"] == 1
    assert numbers["new_ids_by_kind_of_file"] == {"settings": 1, "source": 1}
    assert numbers["new_ids_on_the_ledger_by_kind"] == {"topic": 1}
    assert ids_in_code.main(["--repositories", "0"]) == 2


def test_only_an_id_made_in_the_window_and_named_by_one_code_would_give_a_proof() -> None:
    repositories = {
        "https://github.com/a/made-in-time": Drawn(windows=(EVENT,)),
        "https://github.com/a/proof-already": Drawn(windows=(EVENT,), proof_now=True),
        "https://github.com/a/made-long-ago": Drawn(windows=(EVENT,)),
        "https://github.com/a/shared-one": Drawn(windows=(EVENT,)),
        "https://github.com/a/shared-two": Drawn(windows=(EVENT,)),
        "https://github.com/a/no-window": Drawn(),
    }
    read = {
        "https://github.com/a/made-in-time": IdsInCode(1, {"0.0.5000001": {"source"}}),
        "https://github.com/a/proof-already": IdsInCode(1, {"0.0.5000002": {"settings"}}),
        "https://github.com/a/made-long-ago": IdsInCode(1, {"0.0.5000003": {"source"}}),  # a token
        "https://github.com/a/shared-one": IdsInCode(1, {"0.0.5000004": {"source"}}),
        "https://github.com/a/shared-two": IdsInCode(1, {"0.0.5000004": {"source"}}),
        "https://github.com/a/no-window": IdsInCode(1, {"0.0.5000005": {"source"}}),
    }
    in_time = datetime(2026, 9, 20, tzinfo=UTC)
    ledger = {"0.0.5000001": made("0.0.5000001", in_time),
              "0.0.5000002": made("0.0.5000002", in_time),
              "0.0.5000003": made("0.0.5000003", datetime(2023, 3, 1, tzinfo=UTC), "token"),
              "0.0.5000004": made("0.0.5000004", in_time),
              "0.0.5000005": made("0.0.5000005", in_time)}  # fmt: skip
    numbers = measure(repositories, read, set(), ledger)
    assert numbers["repositories_with_a_new_own_id_on_the_ledger"] == 6
    assert numbers["new_ids_in_the_code_of_two_drawn_repositories"] == 2  # counted in each
    assert numbers["repositories_with_a_new_id_made_in_the_window"] == 2
    assert numbers["repositories_that_would_gain_a_proof"] == 1  # the other has a proof today
    assert numbers["repositories_with_no_event_window"] == 1
    assert numbers["repositories_with_a_proof_now"] == 1
