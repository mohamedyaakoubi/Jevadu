"""The review sheet of Test 1 in a real browser: a grader's answers are kept, saved to a file and
opened again. Every project here is invented.

A grader spends hours on this sheet, and a page that loses the grades loses that time. Only a
browser runs the code of the page, so these tests drive one (Playwright, with its Chromium). They
are skipped where that browser is not installed: python -m playwright install chromium.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from evals.test1.sheet import write_sheet
from sheetfakes import made

sync_api = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def browser() -> Iterator[object]:
    with sync_api.sync_playwright() as driver:
        try:
            chromium = driver.chromium.launch()
        except sync_api.Error as error:
            pytest.skip(f"no Chromium for Playwright here: {error.message.splitlines()[0]}")
        yield chromium
        chromium.close()


@pytest.fixture
def sheet(tmp_path: Path) -> tuple[Path, dict]:
    data, key = made(count=3, seed=5)
    return write_sheet(tmp_path / "sheet", data, key), data


def opened(browser: object, path: Path) -> object:
    """The sheet in a new browser, with nothing kept from another test. Where no file can be
    chosen, the sheet downloads the grades: the tests use that way."""
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    page.add_init_script("delete window.showSaveFilePicker;")
    page.goto(path.as_uri())
    return page


def answer_before_the_card(page: object, category: str = "Health") -> None:
    page.get_by_label(category, exact=True).check()
    page.locator("#before input[type=checkbox][value=consensus]").check()
    page.locator('#before [data-group="parser"] button[data-value="same"]').click()


def grade_every_field(page: object) -> None:
    for field in page.locator("#card article.field").all():
        for group, value in (("grade", "right"), ("label", "right"), ("has_it", "no")):
            buttons = field.locator(f'[data-group="{group}"] button[data-value="{value}"]')
            if buttons.count():
                buttons.click()


def kept(page: object, data: dict) -> dict:
    return page.evaluate(f"JSON.parse(localStorage.getItem('test1-grades-{data['fingerprint']}'))")


def test_the_card_opens_only_after_the_questions_before_it(browser: object, sheet: tuple) -> None:
    path, _ = sheet
    page = opened(browser, path)
    assert page.locator("#open-card").is_disabled()
    assert page.locator("#card").count() == 0
    answer_before_the_card(page)
    assert page.locator("#open-card").is_enabled()
    page.locator("#open-card").click()
    assert page.locator("#card article.field").count() == 7
    assert page.get_by_label("Health", exact=True).is_disabled()  # closed: the card is shown
    page.get_by_text("I made a mistake").click()
    assert page.get_by_label("Health", exact=True).is_enabled()
    page.context.close()


def test_the_grades_are_kept_in_the_browser_and_come_back_after_a_reload(
    browser: object, sheet: tuple
) -> None:
    path, data = sheet
    page = opened(browser, path)
    answer_before_the_card(page)
    page.locator("#open-card").click()
    grade_every_field(page)
    assert page.locator("#left").inner_text() == "This project is done."
    assert page.locator("#progress").inner_text() == "1 of 3 projects done"
    first = data["cases"][0]["page"]
    saved = kept(page, data)["cases"][first]
    assert saved["category"] == "Health" and saved["services"] == ["consensus"]
    assert saved["fields"]["what_it_does"] == {"grade": "right", "label": "right"}
    assert saved["fields"]["problem"] == {"has_it": "no"}
    page.reload()
    assert page.locator("#progress").inner_text() == "1 of 3 projects done"
    # Five filled fields with two answers each, and two empty fields with one.
    assert page.locator('#card [aria-pressed="true"]').count() == 5 * 2 + 2
    page.context.close()


def test_the_grades_are_saved_to_a_file_and_opened_again(
    browser: object, sheet: tuple, tmp_path: Path
) -> None:
    path, data = sheet
    page = opened(browser, path)
    answer_before_the_card(page)
    with page.expect_download() as download:
        page.locator("#save").click()
    saved = tmp_path / "grades-maintainer.json"
    download.value.save_as(saved)
    assert download.value.suggested_filename == "grades-maintainer.json"
    grades = json.loads(saved.read_text(encoding="utf-8"))
    first = data["cases"][0]["page"]
    assert grades["sheet"] == data["fingerprint"] and grades["grader"] == "maintainer"
    assert grades["cases"][first]["category"] == "Health"
    assert "Downloaded at" in page.locator("#status").inner_text()
    page.context.close()

    grades["cases"][first]["category"] = "Education"
    saved.write_text(json.dumps(grades), encoding="utf-8")
    other = tmp_path / "other.json"
    other.write_text(json.dumps({**grades, "sheet": "f" * 64}), encoding="utf-8")
    page = opened(browser, path)
    page.locator("#open-file").set_input_files(str(other))
    sync_api.expect(page.locator("#status")).to_contain_text("another sheet")
    assert not page.get_by_label("Education", exact=True).is_checked()
    page.locator("#open-file").set_input_files(str(saved))
    sync_api.expect(page.get_by_label("Education", exact=True)).to_be_checked()
    assert kept(page, data)["cases"][first]["category"] == "Education"
    page.context.close()


def test_a_quote_is_marked_in_the_page(browser: object, sheet: tuple) -> None:
    path, data = sheet
    page = opened(browser, path)
    answer_before_the_card(page)
    page.locator("#open-card").click()
    page.locator('article[data-field="hedera_services"] .quotes button').first.click()
    quote = data["cases"][0]["card"]["hedera_services"]["quotes"][0]["text"]
    assert page.locator("#page mark").inner_text() == quote.rstrip(".")
    page.context.close()
