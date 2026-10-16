"""How a set of pages of a test is read (design 13.1). The sets are drawn by evals/sets.py.

A set file is JSON with a list of cases; each case names the address of a page. The steps that
read only some pages, such as the cards of the LLM, take their pages from such a file.
"""

from __future__ import annotations

import json
from pathlib import Path


class SetError(ValueError):
    """A set file cannot be read, or would be written over."""


def pages_of(path: Path) -> list[str]:
    """The addresses of the pages of a set file."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        pages = [str(case["page"]) for case in record["cases"]]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SetError(f"{path.name} cannot be read as a set") from error
    if not pages or len(set(pages)) != len(pages):
        raise SetError(f"{path.name} has no page, or the same page twice")
    return pages
