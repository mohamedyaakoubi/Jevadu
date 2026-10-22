"""Hedera ids in a text. Every text here is invented, and so is every id."""

from __future__ import annotations

import pytest

from hackathon_memory.parse.hedera_ids import (
    ACCOUNT,
    CONTRACT,
    FIRST_USER_NUMBER,
    SCHEDULE,
    TOKEN,
    TOPIC,
    TRANSACTION,
    FoundId,
    find_ids,
)


def ids(*texts: str) -> list[tuple[str, str | None, str | None]]:
    """The id, the network and the kind of each id found."""
    return [(found.entity_id, found.network, found.said_kind) for found in find_ids(*texts)]


# --------------------------------------------------------------------- what is an id


def test_an_id_is_found_with_the_words_around_it() -> None:
    text = "The coin is the token 0.0.2345671 on the test network. The idea is invented."
    assert find_ids(text) == [
        FoundId(
            "0.0.2345671",
            "testnet",
            TOKEN,
            "The coin is the token 0.0.2345671 on the test network. The idea is invented.",
        )
    ]


@pytest.mark.parametrize(
    "text",
    [
        "The version of the page is 0.0.1.",
        "We ship v0.0.3 today and v0.0.12345 next week.",
        "It needs the package sdk@0.0.5000000 to run.",
        "The build 1.0.0.2345678 is the last one.",
        "The release 0.0.3-beta is out, and 0.0.42-alpha follows.",
        "Fees go to the account 0.0.98 and the node is 0.0.3.",
        f"The number 0.0.{FIRST_USER_NUMBER - 1} belongs to the network itself.",
        "A longer number such as 0.0.2345671.9 is not an id.",
        "Glued to letters, x0.0.2345678 and 0.0.2345671x are not ids.",
        "A number that starts with a zero, 0.0.0234567, is not an id.",
        "The address 0x00000000000000000000000000000000002345ab is on some chain.",
    ],
)
def test_a_version_a_number_of_the_network_or_a_bare_address_is_not_an_id(text: str) -> None:
    assert find_ids(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Set HEDERA_OPERATOR_ID=0.0.12345 in the file .env.",
        "An account ID looks like 0.0.1234.",
        "An example payer, 0.0.123456789@1700000000.1, sends it.",
        "The merchant 0.0.54321 and the buyer 0.0.67890 are examples.",
        "A file such as 0.0.98765 holds it.",
        "https://hashscan.io/testnet/account/0.0.123456",
    ],
)
def test_a_number_whose_digits_count_up_or_down_is_an_example(text: str) -> None:
    """In the collection, every such number is an example (22 October 2026)."""
    assert find_ids(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "The local node gave us the accounts 0.0.1002, 0.0.1003 and 0.0.1031.",
        "Our script asks the local node about 0.0.1012.",
        "The local network wrote the transfer 0.0.1004@1700000000.5.",
        "https://hashscan.io/testnet/account/0.0.1022",
    ],
)
def test_the_default_accounts_of_a_local_network_are_not_ids(text: str) -> None:
    """A local Hedera network gives its default accounts the numbers 0.0.1002 to 0.0.1031
    (hiero-local-node's README, read on 22 October 2026)."""
    assert find_ids(text) == []


def test_the_numbers_next_to_the_local_default_accounts_are_ids() -> None:
    assert ids("The account 0.0.1001, and the topic 0.0.1032.") == [
        ("0.0.1001", None, ACCOUNT),
        ("0.0.1032", None, TOPIC),
    ]


def test_a_number_that_counts_only_in_part_is_an_id() -> None:
    assert ids("The token 0.0.1235 and the topic 0.0.123451.") == [
        ("0.0.1235", None, TOKEN),
        ("0.0.123451", None, TOPIC),
    ]


def test_the_first_number_that_a_user_can_own_is_an_id() -> None:
    assert ids(f"Our account is 0.0.{FIRST_USER_NUMBER}.") == [
        (f"0.0.{FIRST_USER_NUMBER}", None, ACCOUNT)
    ]


@pytest.mark.parametrize(
    "text",
    [
        "The log is the topic 0.0.3456781.",
        "The log is the topic (0.0.3456781), as said.",
        "TOPIC_ID=0.0.3456781",
        "topicId: 0.0.3456781;",
        "The topic 0.0.3456781-vfmkw has a check word.",
        "The topic 0.0.3456781-based log.",
        "path/of/the/topic/0.0.3456781/messages",
    ],
)
def test_an_id_is_found_whatever_stands_next_to_it(text: str) -> None:
    assert ids(text) == [("0.0.3456781", None, TOPIC)]


# --------------------------------------------------------------------- the network


@pytest.mark.parametrize(
    ("text", "network"),
    [
        ("The token 0.0.2345671 lives on mainnet.", "mainnet"),
        ("On the Main Net the token is 0.0.2345671.", "mainnet"),
        ("Deployed to the test-net: token 0.0.2345671.", "testnet"),
        ("The Hedera Test Network holds the token 0.0.2345671.", "testnet"),
        ("Token 0.0.2345671 (previewnet).", "previewnet"),
        ("HEDERA_NETWORK=testnet\nTOKEN_ID=0.0.2345671", "testnet"),
        ("The token 0.0.2345671 is live.", None),
        ("The latest network contest gave us the token 0.0.2345671.", None),
    ],
)
def test_the_network_is_the_one_that_the_words_near_the_id_name(
    text: str, network: str | None
) -> None:
    assert ids(text) == [("0.0.2345671", network, TOKEN)]


def test_two_networks_near_an_id_leave_its_network_open() -> None:
    # A wrong network is worse than none: the ledger would be asked about another thing.
    text = "On mainnet the token is 0.0.1111111, and on testnet it is 0.0.2222222."
    assert ids(text) == [("0.0.1111111", None, TOKEN), ("0.0.2222222", None, None)]


def test_a_network_named_on_the_line_wins_against_one_named_before() -> None:
    text = "We tested on testnet for a week.\nThe mainnet token is 0.0.2345671."
    assert ids(text) == [("0.0.2345671", "mainnet", TOKEN)]


def test_a_network_named_far_before_the_line_does_not_count() -> None:
    text = "We run on testnet.\n" + "Words that say nothing. " * 12 + "\nThe token is 0.0.2345671."
    assert ids(text) == [("0.0.2345671", None, TOKEN)]


# --------------------------------------------------------------------- what the id is


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Account 0.0.2345671 pays.", ACCOUNT),
        ("Our wallet is 0.0.2345671.", ACCOUNT),
        ("OPERATOR_ID=0.0.2345671", ACCOUNT),
        ("The treasury (0.0.2345671) holds the supply.", ACCOUNT),
        ("Token ID: 0.0.2345671", TOKEN),
        ("The NFTs of 0.0.2345671 are tickets.", TOKEN),
        ("HTS 0.0.2345671", TOKEN),
        ("tokenId = 0.0.2345671", TOKEN),
        ("HCS 0.0.2345671", TOPIC),
        ("Topics: 0.0.2345671", TOPIC),
        ("The contract 0.0.2345671 keeps the rules.", CONTRACT),
        ("CONTRACT_ID=0.0.2345671", CONTRACT),
        ("0.0.2345671 (topic)", TOPIC),
        ("The deadline schedule 0.0.2345671 releases the escrow.", SCHEDULE),
        ("scheduleId: 0.0.2345671", SCHEDULE),
        ("We keep all rights, see 0.0.2345671.", None),
        ("Three nights of work gave 0.0.2345671.", None),
        ("It is 0.0.2345671.", None),
    ],
)
def test_the_word_next_to_an_id_says_what_it_is(text: str, kind: str | None) -> None:
    assert ids(text) == [("0.0.2345671", None, kind)]


def test_the_word_before_an_id_counts_and_not_the_word_before_the_next_id() -> None:
    assert ids("Token ID: 0.0.1111111, Topic ID: 0.0.2222222, account 0.0.3333333") == [
        ("0.0.1111111", None, TOKEN),
        ("0.0.2222222", None, TOPIC),
        ("0.0.3333333", None, ACCOUNT),
    ]


def test_a_word_on_another_line_says_nothing_about_an_id() -> None:
    assert ids("The token of the shop\n0.0.2345671\nand the topic of the log") == [
        ("0.0.2345671", None, None)
    ]


def test_a_word_far_from_an_id_says_nothing_about_it() -> None:
    text = "The token " + "is a thing that many people like to hold and " * 2 + "0.0.2345671."
    assert ids(text) == [("0.0.2345671", None, None)]


# --------------------------------------------------------------------- links to HashScan


def test_a_hashscan_link_says_the_network_and_the_kind_exactly() -> None:
    found = find_ids("See https://hashscan.io/testnet/topic/0.0.3456781 for the log.")
    assert found == [
        FoundId(
            "0.0.3456781",
            "testnet",
            TOPIC,
            "See https://hashscan.io/testnet/topic/0.0.3456781 for the log.",
            True,
        )
    ]


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("https://hashscan.io/mainnet/account/0.0.2345671", ("0.0.2345671", "mainnet", ACCOUNT)),
        ("https://hashscan.io/mainnet/token/0.0.2345671.", ("0.0.2345671", "mainnet", TOKEN)),
        ("hashscan.io/previewnet/contract/0.0.2345671", ("0.0.2345671", "previewnet", CONTRACT)),
        ("https://hashscan.io/testnet/schedule/0.0.2345671", ("0.0.2345671", "testnet", SCHEDULE)),
        ("https://HashScan.io/Testnet/Token/0.0.2345671", ("0.0.2345671", "testnet", TOKEN)),
        (
            "https://hashscan.io/testnet/contract/0x00000000000000000000000000000000002345AB.",
            ("0x00000000000000000000000000000000002345ab", "testnet", CONTRACT),
        ),
        (
            "https://hashscan.io/mainnet/address/0x00000000000000000000000000000000002345ab",
            ("0x00000000000000000000000000000000002345ab", "mainnet", None),
        ),
    ],
)
def test_what_a_hashscan_link_gives(link: str, expected: tuple[str, str, str | None]) -> None:
    assert ids(link) == [expected]
    assert find_ids(link)[0].in_hashscan_link


@pytest.mark.parametrize(
    "link",
    [
        "https://hashscan.io/testnet/transaction/0.0.2345671@1700000000.123456789",
        "https://hashscan.io/testnet/transaction/0.0.2345671-1700000000-123456789",
    ],
)
def test_a_transaction_link_gives_the_transaction_and_the_account_that_paid(link: str) -> None:
    """Both forms give the transaction in the form the mirror node asks for (measured on
    18 October 2026: it refuses the form with "@")."""
    assert ids(link) == [
        ("0.0.2345671", "testnet", ACCOUNT),
        ("0.0.2345671-1700000000-123456789", "testnet", TRANSACTION),
    ]


def test_a_transaction_in_the_text_is_found_with_its_payer() -> None:
    # The digits after the dot are the start of the nanoseconds; a full stop ends a sentence.
    assert ids("Our transfer: 0.0.2345671@1700000000.12.") == [
        ("0.0.2345671-1700000000-120000000", None, TRANSACTION),
        ("0.0.2345671", None, ACCOUNT),
    ]
    assert ids("on testnet, tx 0.0.2345671-1700000000-5 went through") == [
        ("0.0.2345671-1700000000-5", "testnet", TRANSACTION),
        ("0.0.2345671", "testnet", ACCOUNT),
    ]
    assert ids("v0.0.2345678@1700000000.1", "0.0.98@1700000000.1") == []  # not an id


@pytest.mark.parametrize(
    "link",
    [
        "https://hashscan.io/testnet/transaction/1700000000.123456789",  # a time, not an id
        "https://hashscan.io/testnet/account/0.0.98",  # a number of the network itself
        "https://hashscan.io/testnet/dashboard",
        "https://hashscan.example.test/testnet/contract/0x00000000000000000000000000000000002345ab",
    ],
)
def test_a_link_that_names_no_id_of_a_project_gives_nothing(link: str) -> None:
    assert find_ids(link) == []


# --------------------------------------------------------------------- one id, several places


def test_an_id_is_given_once_and_the_place_that_tells_more_is_kept() -> None:
    found = find_ids(
        "We wrote to 0.0.3456781 all week.",
        "The log is the topic 0.0.3456781.",
        "https://hashscan.io/testnet/topic/0.0.3456781",
    )
    assert found == [
        FoundId(
            "0.0.3456781", "testnet", TOPIC, "https://hashscan.io/testnet/topic/0.0.3456781", True
        )
    ]


def test_an_id_named_on_two_networks_is_given_for_each() -> None:
    text = "Testnet token: 0.0.2345671\nMainnet token: 0.0.2345671"
    assert ids(text) == [("0.0.2345671", "testnet", TOKEN), ("0.0.2345671", "mainnet", TOKEN)]


def test_what_one_place_says_about_the_kind_serves_the_other_place() -> None:
    assert ids("The topic 0.0.3456781 is the log.", "On testnet we use 0.0.3456781.") == [
        ("0.0.3456781", "testnet", TOPIC)
    ]


def test_the_ids_come_in_the_order_of_their_first_place() -> None:
    text = "token 0.0.2222222, topic 0.0.1111111, token 0.0.2222222 again"
    assert [found.entity_id for found in find_ids(text, "account 0.0.3333333")] == [
        "0.0.2222222",
        "0.0.1111111",
        "0.0.3333333",
    ]


def test_the_words_around_an_id_are_kept_as_they_stand_with_plain_spaces() -> None:
    text = "before " * 30 + "the\ttopic\n  0.0.3456781   holds   " + "after " * 30
    words = find_ids(text)[0].words_around
    assert "the topic 0.0.3456781 holds after" in words
    assert len(words) < 170
    assert "  " not in words


def test_a_text_with_no_id_gives_nothing() -> None:
    assert find_ids() == []
    assert find_ids("", "A text about Hedera with no id at all.") == []
