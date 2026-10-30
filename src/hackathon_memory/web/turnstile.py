"""Cloudflare's Turnstile on the public copy (design 12.5, 30 October 2026).

Before a visitor of the public copy asks Gemini, checks a submission, reads a project again or
registers one, Cloudflare's Turnstile says whether they are a person (web/public.py). Its widget
runs on the page and, for most visitors, asks nothing; it gives a token, which the page sends to
the server at once. The server spends the token here, with Cloudflare's siteverify, and keeps the
visitor's pass. A token is spent once and holds for 300 seconds, so one that fails is never sent
again: the page asks the widget for a new one.

Read on 30 October 2026 from Cloudflare's pages (developers.cloudflare.com/turnstile): the
address of siteverify, its form fields (secret, response) and its answer (success, action,
hostname, error-codes); a token holds at most 2048 characters; an action, up to 32 letters,
digits, "_" or "-", comes back in the answer. The visitor's address (remoteip) is not sent:
Cloudflare does not say what a different address does, and a browser may reach Vercel by IPv6
and Cloudflare by IPv4. The widget's own list of names (jevadu.mohamedyaakoubi.com and
jevadu.vercel.app) keeps it to this site.
"""

from __future__ import annotations

import httpx

SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
ACTION = "visitor"  # the page's widget names it; an answer for another action is refused
LONGEST_TOKEN = 2048
SECONDS = 10


class Unreachable(Exception):
    """Cloudflare did not answer, or answered something that is not its JSON."""


def is_person(client: httpx.Client, secret: str, token: str) -> bool:
    """Whether Cloudflare says that the token comes from a person, for this site's action. The
    token is spent, whatever the answer. Raises Unreachable."""
    if not token or len(token) > LONGEST_TOKEN:
        return False
    try:
        response = client.post(SITEVERIFY, data={"secret": secret, "response": token},
                               timeout=SECONDS)  # fmt: skip
        response.raise_for_status()
        answer = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise Unreachable(type(error).__name__) from error
    return answer.get("success") is True and answer.get("action") == ACTION
