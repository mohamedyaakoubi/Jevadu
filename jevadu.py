"""The public copy on Vercel (design 12.5): the module that Vercel loads, as pyproject.toml names
it. The site's code lives under src/, which Vercel reads as files rather than as an installed
package, so that folder goes on the path first (web/vercel_app.py makes the site)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from hackathon_memory.web.vercel_app import app  # noqa: E402

__all__ = ["app"]
