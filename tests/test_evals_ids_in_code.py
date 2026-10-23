"""The measure of the Hedera IDs in the code of a repository (evals/ids_in_code.py), on invented
archives and invented IDs."""

from __future__ import annotations

import io

from evals import ids_in_code
from evals.ids_in_code import IdsInCode, kind_of_file, measure, scan_ids
from fakes import archive
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


def test_the_numbers_count_new_ids_and_those_on_the_ledger() -> None:
    repositories = {"https://github.com/a/one": {"0.0.4870201"}, "https://github.com/a/two": set(),
                    "https://github.com/a/gone": set()}  # fmt: skip
    read = {
        "https://github.com/a/one": IdsInCode(5, {"0.0.4870201": {"source"},
                                                    "0.0.4870202": {"settings"}}),
        "https://github.com/a/two": IdsInCode(2, {"0.0.4870203": {"source"}}),
        "https://github.com/a/gone": None,
    }  # fmt: skip
    ledger = {"0.0.4870202": {"testnet"}, "0.0.4870203": set()}
    numbers = measure(repositories, read, {"0.0.4870202"}, ledger)
    assert numbers["repositories_read"] == 2 and numbers["archives_not_read"] == 1
    assert numbers["repositories_with_a_new_id_in_code"] == 2
    assert numbers["repositories_with_a_new_id_on_the_ledger"] == 1
    assert numbers["repositories_with_a_new_own_id_on_the_ledger"] == 0  # named elsewhere
    assert numbers["new_ids_in_code"] == 2 and numbers["new_ids_on_the_ledger"] == 1
    assert numbers["new_ids_by_kind_of_file"] == {"settings": 1, "source": 1}
    assert ids_in_code.main(["--repositories", "0"]) == 2
