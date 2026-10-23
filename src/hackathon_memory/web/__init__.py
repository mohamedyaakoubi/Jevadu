"""The website (design 12): pages made on the server, with FastAPI.

    python -m hackathon_memory.web            serves it on http://127.0.0.1:8000

S1, the search, and S2, the project card. The facts come from the tables, never from a model
(design rule 2). The fields written by a model always show their label and their quotes (design
rule 3), and nothing on a page scores, ranks or judges a project (design rule 1).
"""
