"""The example ideas that the search screen offers under its box (design 8.2, web/app.py).

They are the tool's own words, not a person's, and every visitor may click them. So what the
search learns about them is kept for good: the embedding of the idea (db/embeddings.py), and the
order and the comparisons of the search model (db/idea_answers.py). After the first time, a click
on an example never waits for Google and costs nothing. A typed idea is kept for one day.
"""

EXAMPLE_IDEAS = (
    "limits on what an AI agent may spend",
    "tracking coffee from the farm to the cup",
    "a ticket market without scalpers",
)
