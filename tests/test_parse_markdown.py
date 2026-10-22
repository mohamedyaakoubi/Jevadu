"""People are taken out of a Markdown text before it is saved. Every README here is invented."""

from __future__ import annotations

import pytest

from hackathon_memory.parse.markdown import (
    TEAM_TITLES,
    hide_in_markdown,
    is_team_title,
    names_a_part_of_the_project,
    title_key,
)
from hackathon_memory.parse.people import (
    HIDDEN_ADDRESS,
    HIDDEN_HANDLE,
    HIDDEN_LINK,
    HIDDEN_PHOTO,
)

README = """# Pebble Pay

Pay a street vendor with a coin on Hedera.

## Features

- A buyer signs one payment on the testnet topic 0.0.3456781.

## Team

| Name | Role |
|---|---|
| Quill Invented | Frontend |
| Reed Invented | Contracts |

### Quill Invented

Builds the web page. [LinkedIn](https://www.linkedin.com/in/quill-invented)

## Installation

```bash
npm install @sample-scope/sdk
git config user.email quill@example.test
```

Ask @fern_invented if it fails.
"""


# --------------------------------------------------------------------- the part about the team


def test_the_part_about_the_team_is_cut_out_with_its_inner_parts() -> None:
    done = hide_in_markdown(README)
    assert "Quill Invented" not in done.text
    assert "Reed Invented" not in done.text
    assert "## Team" not in done.text
    assert done.team_parts_cut == 1
    assert done.team_lines_cut == 11  # from "## Team" to the line before "## Installation"
    assert done.ids_in_the_cut == 0
    # What is around it stays word for word.
    assert "## Features\n\n- A buyer signs one payment on the testnet topic 0.0.3456781." in (
        done.text
    )
    assert "## Installation\n\n```bash\nnpm install @sample-scope/sdk\n" in done.text


def test_in_code_only_the_address_is_hidden_and_in_the_rest_the_handle_too() -> None:
    done = hide_in_markdown(README)
    assert f"git config user.email {HIDDEN_ADDRESS}" in done.text
    assert "npm install @sample-scope/sdk" in done.text
    assert f"Ask {HIDDEN_HANDLE} if it fails." in done.text
    assert done.words_hidden == 2


@pytest.mark.parametrize(
    "title",
    [
        "## Team",
        "## 👥 Our Team",
        "### Team: Pebble Builders",
        "## The Team - Pebble",
        "#### **Meet the team**",
        '<h2 align="center">Contributors</h2>',
        "## Contact",
        "# Built by",
    ],
)
def test_a_title_about_the_team_is_known_in_its_many_shapes(title: str) -> None:
    done = hide_in_markdown(f"# Pebble\n\nText.\n\n{title}\n\nQuill Invented\n")
    assert "Quill" not in done.text
    assert done.team_parts_cut == 1


@pytest.mark.parametrize(
    "title",
    [
        "## Team management",  # a feature for teams
        "## Contributing",  # how to help, not who helped
        "## Teamwork",
        "## Members area",
        "## Acknowledgements",
    ],
)
def test_a_title_that_is_not_about_the_team_cuts_nothing(title: str) -> None:
    text = f"# Pebble\n\n{title}\n\nSome words.\n"
    done = hide_in_markdown(text)
    assert done.text == text
    assert done.team_parts_cut == 0


def test_a_title_of_the_other_kind_is_known_too() -> None:
    text = "Pebble\n======\n\nText.\n\nTeam\n----\n\nQuill Invented\n\nSetup\n-----\n\nRun it.\n"
    done = hide_in_markdown(text)
    assert done.text == "Pebble\n======\n\nText.\n\nSetup\n-----\n\nRun it.\n"
    assert done.team_lines_cut == 5


def test_a_part_about_the_team_ends_at_a_title_that_names_a_part_of_the_project() -> None:
    # A team part with a high title would else take the rest of the README with it.
    text = "# Pebble\n\n# Team\n\nQuill Invented\n\n## Installation\n\nRun it.\n"
    done = hide_in_markdown(text)
    assert done.text == "# Pebble\n\n## Installation\n\nRun it.\n"


def test_a_hedera_id_in_a_part_that_is_cut_is_counted_and_not_kept() -> None:
    text = "# Pebble\n\n## Team\n\nQuill runs the account 0.0.1234561 and the topic 0.0.7654329.\n"
    done = hide_in_markdown(text)
    assert done.ids_in_the_cut == 2
    assert "0.0.1234561" not in done.text


def test_two_parts_about_the_team_are_two() -> None:
    text = "# Pebble\n\n## Team\n\nQuill\n\n## Contact\n\nReed\n\n## License\n\nMIT\n"
    done = hide_in_markdown(text)
    assert done.team_parts_cut == 2
    assert done.text == "# Pebble\n\n## License\n\nMIT\n"


def test_a_title_inside_code_is_not_a_title() -> None:
    text = "# Pebble\n\n```markdown\n## Team\nQuill\n```\n\nThe end.\n"
    done = hide_in_markdown(text)
    assert done.text == text
    assert done.team_parts_cut == 0


def test_a_fence_of_tildes_and_a_longer_fence_are_closed_rightly() -> None:
    text = "~~~~\n```\n@quill_invented stays: this is code\n~~~~\n\nAsk @reed.\n"
    done = hide_in_markdown(text)
    assert (
        done.text
        == f"~~~~\n```\n@quill_invented stays: this is code\n~~~~\n\nAsk {HIDDEN_HANDLE}.\n"
    )


# --------------------------------------------------------------------- links and photos


def test_a_link_to_a_profile_goes_with_its_words() -> None:
    text = "Made by [Quill Invented](https://x.com/quill_invented) and [Reed](https://github.com/reed)."
    done = hide_in_markdown(text)
    assert done.text == f"Made by {HIDDEN_LINK} and {HIDDEN_LINK}."
    assert done.words_hidden == 2


def test_a_link_to_code_or_to_a_page_stays() -> None:
    text = (
        "See [the code](https://github.com/sample-org/pebble-pay) and "
        "[the topic](https://hashscan.io/testnet/topic/0.0.3456781)."
    )
    assert hide_in_markdown(text).text == text


def test_photos_of_accounts_are_hidden_in_markdown_and_in_html() -> None:
    text = (
        "![Quill](https://avatars.githubusercontent.com/u/1234567?v=4)\n"
        '<img src="https://avatars.githubusercontent.com/u/7654321" width="80" alt="Reed">\n'
        '<a href="https://github.com/quill_invented"><b>Quill Invented</b></a>\n'
        "![logo](https://raw.githubusercontent.com/sample-org/pebble-pay/main/logo.png)\n"
    )
    done = hide_in_markdown(text)
    assert done.text == (
        f"{HIDDEN_PHOTO}\n{HIDDEN_PHOTO}\n{HIDDEN_LINK}\n"
        "![logo](https://raw.githubusercontent.com/sample-org/pebble-pay/main/logo.png)\n"
    )
    assert done.words_hidden == 3


def test_inline_code_keeps_its_signs_and_loses_an_address() -> None:
    text = "Use `@sample-scope/sdk` with `quill@example.test`, ask @quill."
    done = hide_in_markdown(text)
    assert done.text == f"Use `@sample-scope/sdk` with `{HIDDEN_ADDRESS}`, ask {HIDDEN_HANDLE}."


# --------------------------------------------------------------------- what stays the same


def test_a_readme_with_no_word_about_people_stays_letter_for_letter() -> None:
    text = "# Pebble\r\n\r\nPay with a coin.\r\n\r\n## Setup\r\n\r\n```\r\nnpm i\r\n```\r\n"
    done = hide_in_markdown(text)
    assert done.text == text
    assert (done.words_hidden, done.team_parts_cut, done.team_lines_cut) == (0, 0, 0)


def test_taking_people_out_twice_changes_nothing_more() -> None:
    once = hide_in_markdown(README)
    twice = hide_in_markdown(once.text)
    assert twice.text == once.text
    assert (twice.words_hidden, twice.team_parts_cut) == (0, 0)


def test_no_name_of_the_invented_people_is_left() -> None:
    text = hide_in_markdown(README).text
    for name in ("quill", "Quill", "reed", "Reed", "fern"):
        assert name not in text


# --------------------------------------------------------------------- the titles


def test_the_key_of_a_title_has_no_signs_no_emoji_and_no_name_after_a_colon() -> None:
    assert title_key("## 👥 **Our Team**") == "our team"
    assert title_key("Team: Pebble Builders") == "team"
    assert title_key("Team – Pebble") == "team"
    assert title_key("<b>Contributors</b> 🙌") == "contributors"
    assert title_key("[Team](#team)") == "team"


def test_every_team_title_is_written_as_its_own_key() -> None:
    assert all(title_key(title) == title for title in TEAM_TITLES)
    assert is_team_title("Meet The Team!")


def test_a_title_about_a_part_of_the_project_is_not_a_team_title() -> None:
    assert names_a_part_of_the_project("## Installation")
    assert names_a_part_of_the_project("Hedera services used")
    assert not names_a_part_of_the_project("Contributors")
    assert not names_a_part_of_the_project("Builders")  # a team title wins
