"""The public copy on Vercel (design 12.5, 29 October 2026): the module that Vercel loads
(pyproject.toml, [tool.vercel]).

Vercel runs the site as functions. The folder of the deployment is read-only, only /tmp may be
written, a request may land on any copy of the site, and nothing runs between requests. So:

* the site is made with `serverless=True` (web/app.py): a check and a reading again are done
  within their request, and no round runs in the background;
* the data folder is made again in /tmp when a copy starts: the saved pages and GitHub's saved
  answers are links to the files of the deployment, read as they are, and a new answer is written
  beside them as a file of its own (collect/rawstore.py never writes over a saved answer); the
  counts of requests, which change, are copied;
* the visitor's address is the one that Vercel writes itself, x-vercel-forwarded-for, which a
  visitor cannot give (vercel.com/docs/headers/request-headers, read 29 October 2026).

The settings come from the project's variables on Vercel, never from a file: .env is not sent.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from hackathon_memory.settings import Settings
from hackathon_memory.web.app import create_app

ROOT = Path(__file__).resolve().parents[3]  # the folder of the deployment
WRITABLE = Path("/tmp/jevadu-data")  # noqa: S108  (Vercel lets a function write here only)
LINKED, COPIED = ("raw",), ("requests",)
ADDRESS_HEADER = "x-vercel-forwarded-for"


def linked_copy(source: Path, target: Path) -> None:
    """The folders of `source` again under `target`, with a link to each of its files."""
    for folder, _, files in os.walk(source):
        here = target / Path(folder).relative_to(source)
        here.mkdir(parents=True, exist_ok=True)
        for name in files:
            link = here / name
            if not link.exists():
                link.symlink_to(Path(folder) / name)


def data_folder(bundled: Path, writable: Path) -> Path:
    """The data folder of this copy of the site, made once in `writable` from `bundled`."""
    if not writable.exists():
        for part in LINKED:
            if (bundled / part).is_dir():
                linked_copy(bundled / part, writable / part)
        for part in COPIED:
            if (bundled / part).is_dir():
                shutil.copytree(bundled / part, writable / part)
    writable.mkdir(parents=True, exist_ok=True)
    return writable


def make_app(bundled: Path = ROOT / "data", writable: Path = WRITABLE):  # noqa: ANN201
    settings = Settings()
    hosted = settings.model_copy(update={"data_dir": str(data_folder(bundled, writable)),
                                         "public_address_header": ADDRESS_HEADER})  # fmt: skip
    return create_app(hosted, public=True, serverless=True)


app = make_app() if os.environ.get("VERCEL") else None  # made where Vercel loads it, not in tests
