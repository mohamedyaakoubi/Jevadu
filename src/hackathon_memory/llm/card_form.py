"""The form that the LLM fills for every project (design 4.1, 4.3, 4.5 and 6.2).

This is the one place that says what an LLM field is. The proof of Gate A uses it to check that a
real call returns a valid form, and Phase D builds the quote check and the card on top of it.

Rules of the design that the form carries:

* Every field has a label (4.3): "stated" (the page says it), "inferred" (the LLM worked it out
  from other sentences) or "not_found" (the page gives nothing). An empty field is right only
  when the label is "not_found".
* Every filled field carries the exact sentences of the page that support it (6.3). A program,
  not the LLM, checks that each sentence is in the page. That check is Phase D.
* The category is one of a fixed list (4.5), chosen by who the project serves.
* IDs, links, dates and counts are not fields here. Facts come from the parser, the code host and
  the ledger, never from the LLM (6.4).

Gemini's structured output takes a simple schema, so the models below have no defaults and no
unions.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

# The version of the instructions below. It is stored with every answer (design 6.5).
# card-form-1, 13 October 2026, written on the 15 tuning pages only (design 13.2): shorter and
# plainer sentences for a reader whose first language is not English (design rule 13), and
# stricter labels, because the first cards called "stated" what a page only suggested.
# card-form-2, 15 October 2026: the list of categories split once (design 4.5), because the two
# graders of Test 1 agreed on 4 of 11 categories, most often on tools built for AI agents.
INSTRUCTIONS_VERSION = "card-form-2"

SYSTEM_INSTRUCTIONS = """\
You read the text of one hackathon project page and fill a form about it.

Rules:
- Use only what the page says. Do not use what you know about the project from elsewhere.
- For each field, give a label. "stated": one sentence of the page says it. "inferred": you put \
it together from several sentences, or the page suggests it without saying it. "not_found": \
the page gives nothing about it.
- For each field that is not "not_found", copy the exact sentences of the page that support it, \
word for word, into "quotes". A quote must be a piece of the page and nothing else.
- A field with the label "not_found" has empty text, no steps and no quotes.
- Do not write Hedera account, token, topic or contract ids, links, dates or numbers as facts.
- Do not score the project, do not rank it, and do not say that it is a copy of anything.
- "category" is the field of life the project serves, not the technology inside. Use \
"AI agents and automation" only when an agent or an automation is what people run or get, \
such as a trading agent or an agent that books travel. Use "Tools for AI agents" when the \
project is built for AI agents to use, such as limits on what an agent may spend, an \
identity or a reputation for agents, or a market where agents buy services. Use "Developer \
tools" when the project is a tool for people who build software. The category is "stated" \
only when the page itself names that field of life; otherwise it is "inferred".
- Write for a reader whose first language is not English: short sentences of at most 20 \
words, common words, and a short explanation for any technical word. "what_it_does" is one \
sentence. Each step of "how_it_works" is one short sentence.
"""


class Label(StrEnum):
    STATED = "stated"
    INFERRED = "inferred"
    NOT_FOUND = "not_found"


class Category(StrEnum):
    """The list of design 4.5. Test 1 did not accept its first version of 16 categories, so it
    was split once, on 15 October 2026: "Tools for AI agents" came out of "AI agents and
    automation"."""

    PAYMENTS = "Payments and remittance"
    LENDING = "Lending, saving and investing"
    ASSETS = "Real-world assets and tokens"
    IDENTITY = "Identity and credentials"
    SUPPLY_CHAIN = "Supply chain and provenance"
    CLIMATE = "Sustainability, energy and climate"
    HEALTH = "Health"
    EDUCATION = "Education"
    AGRICULTURE = "Agriculture"
    GAMING = "Gaming and entertainment"
    SOCIAL = "Social and community"
    AI_AGENTS = "AI agents and automation"
    AGENT_TOOLS = "Tools for AI agents"  # split from AI_AGENTS on 15 October 2026
    DEVELOPER_TOOLS = "Developer tools"
    DATA_DEVICES = "Data and devices"
    PUBLIC_SERVICES = "Public services"
    OTHER = "Other"


class TextField(BaseModel):
    label: Label
    text: str = Field(description="One or two plain sentences. Empty when the label is not_found.")
    quotes: list[str] = Field(description="Exact sentences of the page that support the text.")

    @model_validator(mode="after")
    def _not_found_is_empty(self) -> TextField:
        if self.label is Label.NOT_FOUND and (self.text.strip() or self.quotes):
            raise ValueError("a field labelled not_found must be empty")
        return self


class StepsField(BaseModel):
    label: Label
    steps: list[str] = Field(
        max_length=6, description="How it works, in 3 to 6 short steps. Empty when not_found."
    )
    quotes: list[str] = Field(description="Exact sentences of the page that support the steps.")

    @model_validator(mode="after")
    def _not_found_is_empty(self) -> StepsField:
        if self.label is Label.NOT_FOUND and (self.steps or self.quotes):
            raise ValueError("a field labelled not_found must be empty")
        return self


class CategoryField(BaseModel):
    label: Label
    category: Category
    quotes: list[str] = Field(description="Exact sentences of the page that support the choice.")


class CardFields(BaseModel):
    """The fields that only an LLM can fill (design 4.1, third row)."""

    what_it_does: TextField = Field(description="One plain sentence on what the project does.")
    how_it_works: StepsField
    for_whom: TextField = Field(description="Who uses it.")
    hedera_services: TextField = Field(
        description="Which Hedera services the page says it uses, and for what."
    )
    category: CategoryField
    problem: TextField = Field(description="The problem, when the page has no titled section.")
    solution: TextField = Field(description="The solution, when the page has no titled section.")

    def all_quotes(self) -> list[str]:
        quotes: list[str] = []
        for field in (
            self.what_it_does,
            self.how_it_works,
            self.for_whom,
            self.hedera_services,
            self.category,
            self.problem,
            self.solution,
        ):
            quotes.extend(field.quotes)
        return quotes
