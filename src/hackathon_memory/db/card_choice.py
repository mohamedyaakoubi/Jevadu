"""Which card of a project the website shows (the maintainer's rule of 1 November 2026).

A card is written by the first model of the settings; when that model keeps answering "too many
requests", a stand-in writes the cards still missing. A project then shows the card of the first
model that wrote one, in the order of the settings (Settings.card_models).
"""

# Joined to a query of projects `p`: `c` is the project's one card, or nothing. Its parameters: the
# list of models, the version of the instructions, and the list of models once more.
CARD_OF_PROJECT = (
    "LEFT JOIN LATERAL (SELECT k.model, k.fields FROM cards k WHERE k.project_id = p.id "
    "AND k.model = ANY(%s) AND k.instructions_version = %s "
    "ORDER BY array_position(%s::text[], k.model) LIMIT 1) c ON true "
)
