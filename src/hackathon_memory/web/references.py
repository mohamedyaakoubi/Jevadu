"""The outside sources that the pages cite, numbered as in an encyclopedia (design 12.1).

A term that a newcomer may not know carries the number of a source that explains it, Hedera's own
documentation first. The numbers are fixed by the order of this list, so a source has the same
number on every page, and the window of sources lists them all in that order. Each address was
opened on 16 October 2026 and answered.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reference:
    key: str
    title: str
    publisher: str
    url: str


DOCS = "https://docs.hedera.com/hedera"
REFERENCES = (
    Reference("hedera", "Hedera documentation", "Hedera", DOCS),
    Reference("ledger", "Distributed ledger", "Wikipedia",
              "https://en.wikipedia.org/wiki/Distributed_ledger"),
    Reference("hashgraph", "Hashgraph consensus algorithm", "Hedera",
              f"{DOCS}/core-concepts/hashgraph-consensus-algorithms"),
    Reference("account", "Accounts", "Hedera", f"{DOCS}/core-concepts/accounts"),
    Reference("topic", "Consensus Service: topics and messages", "Hedera",
              f"{DOCS}/sdks-and-apis/sdks/consensus-service"),
    Reference("token", "Hedera Token Service", "Hedera",
              f"{DOCS}/core-concepts/tokens/hedera-token-service-hts-native-tokenization"),
    Reference("contract", "Smart contracts", "Hedera", f"{DOCS}/core-concepts/smart-contracts"),
    Reference("mirror", "Mirror nodes", "Hedera", f"{DOCS}/core-concepts/mirror-nodes"),
    Reference("explorer", "Network explorers, HashScan among them", "Hedera",
              f"{DOCS}/networks/community-mirror-nodes"),
    Reference("testnet", "The test network", "Hedera", f"{DOCS}/networks/testnet"),
    Reference("mainnet", "The main network", "Hedera", f"{DOCS}/networks/mainnet"),
    Reference("repository", "About repositories", "GitHub Docs",
              "https://docs.github.com/en/repositories/creating-and-managing-repositories/"
              "about-repositories"),
    Reference("embedding", "Get text embeddings", "Google Cloud",
              "https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings/"
              "get-text-embeddings"),
    Reference("bm25", "Okapi BM25", "Wikipedia", "https://en.wikipedia.org/wiki/Okapi_BM25"),
    Reference("gemini", "Google models on Vertex AI", "Google Cloud",
              "https://cloud.google.com/vertex-ai/generative-ai/docs/models"),
    Reference("mtbench", "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena (2023)",
              "Zheng and others, arXiv", "https://arxiv.org/abs/2306.05685"),
    Reference("cvstudy", "AI tools show biases in ranking job applicants' names (2024)",
              "University of Washington",
              "https://www.washington.edu/news/2024/10/31/ai-bias-resume-screening-race-gender/"),
    Reference("sdk", "SDKs", "Hedera", f"{DOCS}/sdks-and-apis/sdks"),  # read on 22 October 2026
)  # fmt: skip
BY_KEY = {reference.key: reference for reference in REFERENCES}
NUMBER = {reference.key: number for number, reference in enumerate(REFERENCES, start=1)}
