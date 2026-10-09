"""A small reader for robots.txt, following RFC 9309.

Python's own `urllib.robotparser` does not understand the wildcards `*` and `$` that most
sites use in their rules, so a Disallow rule with a wildcard could be missed. This reader
understands them. The rules (RFC 9309, section 2.2):

* The group of the most specific matching user agent is used; "*" is the fallback.
* Among the rules of the group, the longest matching path wins. Allow wins a tie.
* No matching rule means the path is allowed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, path pattern)
    crawl_delay: float | None = None


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    ends_here = pattern.endswith("$")
    if ends_here:
        pattern = pattern[:-1]
    body = ".*".join(re.escape(part) for part in pattern.split("*"))
    return re.compile("^" + body + ("$" if ends_here else ""))


class RobotsRules:
    def __init__(self, text: str) -> None:
        self._groups: list[_Group] = []
        current: _Group | None = None
        last_was_agent = False
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = _Group()
                    self._groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if current is None:
                continue
            if key in ("allow", "disallow"):
                # An empty Disallow means "everything is allowed", so it adds no rule.
                if value:
                    current.rules.append((key == "allow", value))
            elif key == "crawl-delay":
                try:
                    current.crawl_delay = float(value)
                except ValueError:
                    pass

    def _group_for(self, agent: str) -> _Group | None:
        agent = agent.lower()
        best: tuple[int, _Group] | None = None
        for group in self._groups:
            for name in group.agents:
                if name == "*":
                    continue
                if name in agent and (best is None or len(name) > best[0]):
                    best = (len(name), group)
        if best is not None:
            return best[1]
        return next((g for g in self._groups if "*" in g.agents), None)

    def allows(self, agent: str, url: str) -> bool:
        group = self._group_for(agent)
        if group is None:
            return True
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        verdict, longest = True, -1
        for allow, pattern in group.rules:
            if _pattern_to_regex(pattern).match(path):
                length = len(pattern)
                if length > longest or (length == longest and allow):
                    verdict, longest = allow, length
        return verdict

    def crawl_delay(self, agent: str) -> float | None:
        group = self._group_for(agent)
        return group.crawl_delay if group else None
