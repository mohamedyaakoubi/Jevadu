"""The cases of Test 2 (design 13.3), judged on 15 October 2026 before the first run.

Two kinds of pairs of projects, judged by the second grader with the rule of guideline.md:

* SAME_IDEA: someone who holds one of the two would say "this was already built": the same users
  and the same main action. Each one must find the other in its first 10 results.
* LOOK_ALIKE: the two share a name, a Hedera ID or a theme, but not the idea. They are shown for
  information: the search may show them, and a person then tells them apart.

No candidate came from the search under test. They came from the same repository, the same
Hedera ID or the same name in two places (design 8.4), and from the 60 pages of Test 1 that the
second grader read in full. The reasons are written in our own words, with no text of a page.
"""

from __future__ import annotations

from dataclasses import dataclass

SAME_IDEA, LOOK_ALIKE = "same idea", "look alike"
SHOWCASE = "https://ethglobal.com/showcase/"
POSTS = "https://hedera.com/blog/these-are-the-winners-of-the-"
AFRICA = "https://hedera-hackathon.hashgraph.swiss/#"


@dataclass(frozen=True)
class Pair:
    first: str
    second: str
    kind: str
    source: str  # where the candidate came from
    reason: str  # why it was judged so, in our own words


def _s(slug: str) -> str:
    return SHOWCASE + slug


PAIRS: tuple[Pair, ...] = (
    # ---------------------------------------------------------------- the same idea
    Pair(_s("yourturn-2-0-od7iw"), _s("yourturn-concierge-6pm36"), SAME_IDEA, "same repository",
         "one team, two events: people get value back from bookings they will not use"),
    Pair(_s("yourturn-2-0-od7iw"), _s("yourturn-zb56r"), SAME_IDEA, "same repository",
         "one team, two events: bookings that people resell or recover value from"),
    Pair(_s("yourturn-concierge-6pm36"), _s("yourturn-zb56r"), SAME_IDEA, "same repository",
         "one team, two events: bookings that people resell or recover value from"),
    Pair(_s("assay-qiz12"), _s("assay-26egq"), SAME_IDEA, "same name",
         "one team, two events: agents check each other's reputation before they pay"),
    Pair(_s("pullquestai-fzdys"), _s("pullquestai-6pncc"), SAME_IDEA, "same name",
         "the same project entered twice: rewards for work on open-source code"),
    Pair(POSTS + "hello-future-apex-hackathon#chargefrog",
         POSTS + "hello-future-ascension-hackathon#chargefrog", SAME_IDEA, "same name",
         "the same network of charging stations for electric cars, in two events"),
    Pair(POSTS + "hello-future-apex-hackathon#golden-needle",
         POSTS + "hello-future-ascension-hackathon#golden-needle", SAME_IDEA, "same name",
         "the same record of building-safety documents, in two events"),
    Pair(POSTS + "hellofuture-hackathon-2-0#hashpress-pioneers",
         POSTS + "2024-hellofuture-hackathon#hashpress-pioneers", SAME_IDEA, "same name",
         "Hedera inside WordPress sites, by the same team in two events"),
    Pair(_s("hedron-msiu8"), AFRICA + "hedron", SAME_IDEA, "same name",
         "the same system of agents that work with each other, described the same way"),
    Pair(_s("merxet-9yn1q"), POSTS + "hello-future-apex-hackathon#merxet", SAME_IDEA,
         "same name", "the same private checkout for shops, with a code to scan"),
    Pair(_s("parkpulse-w84tg"), POSTS + "hello-future-ascension-hackathon#parkpulse", SAME_IDEA,
         "same name", "the same data about parks, and votes of the people who live near them"),
    Pair(POSTS + "hellofuture-hackathon-2-0#savera", POSTS + "2024-hellofuture-hackathon#savera",
         SAME_IDEA, "same name", "the same wallet for saving and paying, in two events"),
    Pair(_s("provenance-chain-8g8a1"), _s("sealsign-o3b90"), SAME_IDEA, "read in Test 1",
         "both put the fingerprint of a document on the ledger so that anyone can check it later"),
    Pair(_s("veiledswap-9esbt"), _s("ztomic-swap-ufv2r"), SAME_IDEA, "read in Test 1",
         "both let traders swap tokens so that nobody can link who swapped what"),
    Pair(_s("fitcentive-mptde"), _s("mind-your-data-5pyj3"), SAME_IDEA, "read in Test 1",
         "both let people keep their health data and decide who may use it, for a price"),
    Pair(_s("assay-26egq"), _s("ctrlz-p8tn8"), SAME_IDEA, "read in Test 1",
         "both decide how one agent pays another from its reputation on the ledger"),
    Pair(_s("allowance-x9syo"), _s("vaultbreaker-xw79k"), SAME_IDEA, "read in Test 1",
         "both keep the payments of an AI agent inside limits that a person set"),
    Pair(_s("allowance-x9syo"), _s("paybound-kcezf"), SAME_IDEA, "read in Test 1",
         "both keep the payments of an AI agent inside limits that a person set"),
    Pair(_s("vaultbreaker-xw79k"), _s("paybound-kcezf"), SAME_IDEA, "read in Test 1",
         "both let an agent pay within limits without ever holding the key that pays"),
    Pair(_s("notyet-hy3kh"), _s("vaultbreaker-xw79k"), SAME_IDEA, "read in Test 1",
         "both give an agent a budget without a key that it could empty"),
    Pair(_s("cubic-g1kwb"), _s("faregate-w3jpz"), SAME_IDEA, "read in Test 1",
         "both put a gateway between an agent and what it does, and fixed rules decide"),
    Pair(_s("ognef-dqsm0"), _s("cubic-g1kwb"), SAME_IDEA, "read in Test 1",
         "both let a person set rules that allow, refuse or escalate each action of an agent"),
    Pair(_s("agentmarket-9cn1t"), _s("mars-ua1qc"), SAME_IDEA, "read in Test 1",
         "both are markets where AI agents find tools and pay for each use"),
    Pair(_s("tenor-8wx00"), _s("galvanic-5g3wr"), SAME_IDEA, "read in Test 1",
         "both let a borrower get cash against a tokenized bond"),
    # ---------------------------------------------------------------- look alike only
    Pair(_s("aegis-93ox5"), _s("aegis-w6727"), LOOK_ALIKE, "same name",
         "a wallet that limits an agent's payments, against an audit of smart contracts"),
    Pair(_s("agentrail-5dppt"), _s("agentrail-1ekv0"), LOOK_ALIKE, "same name",
         "permissions for agents, against a payment gateway for shops"),
    Pair(_s("atlas-4p553"), _s("atlas-w4yw4"), LOOK_ALIKE, "same name",
         "an agent that trades, against an agent that watches the risk of a portfolio"),
    Pair(_s("covenant-kxv95"), _s("covenant-6j7sn"), LOOK_ALIKE, "same name",
         "a watch over a loan, against property tokens that only verified people may hold"),
    Pair(_s("vouch-63ywx"), _s("vouch-gade2"), LOOK_ALIKE, "same name",
         "a check of sensor data before rewards, against a reputation for agents"),
    Pair(POSTS + "hellofuture-hackathon-2-0#acoer-team",
         POSTS + "2024-hellofuture-hackathon#acoer-team", LOOK_ALIKE, "same name",
         "one team, two ideas: tracking medicines, against a record of health predictions"),
    Pair(POSTS + "hellofuture-hackathon-2-0#osmiumlabs",
         POSTS + "2024-hellofuture-hackathon#osmiumlabs", LOOK_ALIKE, "same name",
         "one team, two ideas: digital identity, against a chat that runs Hedera actions"),
    Pair(_s("hedron-msiu8"), POSTS + "hello-future-origins-hackathon#hedron", LOOK_ALIKE,
         "same name", "agents that work with each other, against an agent that guides investors"),
    Pair(_s("froggy-284ag"), _s("onchain-heartbeat-sxze9"), LOOK_ALIKE, "same Hedera ID",
         "a shared payment service: a home for agents, against a narrated feed of the ledger"),
    Pair(_s("reveal-k4mq7"), _s("sotto-ukx6e"), LOOK_ALIKE, "same Hedera ID",
         "a shared token: surprise nights out, against a venue for trading securities"),
    Pair(_s("froggy-284ag"), _s("hands-unchained-6kdf3"), LOOK_ALIKE, "same Hedera ID",
         "a shared ID: a home for agents, against renting a robot arm"),
    Pair(_s("tenor-market-cxywq"), _s("tokenize-it-tsusj"), LOOK_ALIKE, "same Hedera ID",
         "a shared contract: a market for security tokens, against loans on employee shares"),
    Pair(_s("covenant-hedera-4jvyy"), _s("forfait-eam6y"), LOOK_ALIKE, "same Hedera ID",
         "a shared ID: a lending console for private credit, against selling invoices"),
    Pair(_s("accrue-racfy"), _s("adralis-v042p"), LOOK_ALIKE, "read in Test 1",
         "both put ads around AI, but one pays people who wait and one pays agent makers"),
    Pair(_s("chemical-01b4r"), _s("common-arcade-vb6ao"), LOOK_ALIKE, "read in Test 1",
         "one game, against a platform where people and agents play many games"),
)  # fmt: skip
