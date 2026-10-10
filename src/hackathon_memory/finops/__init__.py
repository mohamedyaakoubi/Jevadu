"""What the models cost: FinOps for the Gemini calls.

Every call to a model costs money. This package answers four questions, for the test work and for
the running tool separately:

* What did each call cost? (`prices`, `calls`)
* Can the next call still be paid for? (`budget`)
* Is every call counted, also the one somebody adds next month? (`meter`: the client itself is
  wrapped, so a call cannot go around the count)
* Where does the money go, and what will it cost next? (`report`)

The numbers here are our own count: tokens that Google reported, times the prices that Google
published. The bill of Google Cloud is the truth. `python -m hackathon_memory.finops reconcile`
compares the two.
"""
