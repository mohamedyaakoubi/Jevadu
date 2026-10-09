"""One dated result file per proof run.

Design rule: when something is checked or measured, a file must be left behind.
A result file holds the checks, the numbers and what the proof does not show. It never holds
a secret, and it holds no text taken from a collected page (design rules 9 and 18).
"""

from __future__ import annotations

import json
import platform
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"
MAX_DETAIL = 500  # characters of one detail line


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ProofResult:
    proof: str
    gate: str = "A"
    checks: list[Check] = field(default_factory=list)
    measurements: dict[str, object] = field(default_factory=dict)
    does_not_prove: list[str] = field(default_factory=list)
    ran_at: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    _secrets: list[str] = field(default_factory=list, repr=False)

    def hide(self, *values: str) -> None:
        """Register a value that must never appear in the printed lines or the saved file."""
        self._secrets.extend(v for v in values if v)

    def _scrub(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text

    def check(self, name: str, passed: bool, detail: str = "") -> bool:
        # Scrub first and cut after. A secret that straddles the cut would otherwise stay in part.
        name, detail = self._scrub(name), self._scrub(detail)[:MAX_DETAIL]
        self.checks.append(Check(name, bool(passed), detail))
        mark = "ok  " if passed else "FAIL"
        print(f"[{mark}] {name}" + (f": {detail}" if detail else ""))
        return bool(passed)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    def save(self) -> Path:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = self.ran_at.replace(":", "").replace("-", "")
        path = RESULTS_DIR / f"{stamp}-{self.proof}.json"
        body = {
            "proof": self.proof,
            "gate": self.gate,
            "ran_at": self.ran_at,
            "passed": self.passed,
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "checks": [asdict(c) for c in self.checks],
            "measurements": self.measurements,
            "does_not_prove": self.does_not_prove,
        }
        text = self._scrub(json.dumps(body, indent=2, ensure_ascii=False)) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def finish(self) -> int:
        """Print the verdict, save the file and give the exit code for the shell."""
        path = self.save()
        verdict = "PASSED" if self.passed else "FAILED"
        shown = path.relative_to(RESULTS_DIR.parent.parent).as_posix()
        print(f"\nProof '{self.proof}': {verdict}. Result file: {shown}")
        return 0 if self.passed else 1
