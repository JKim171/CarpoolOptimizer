"""Request and response models.

Responses are **one explicit model per audience**, never a dict with keys conditionally deleted
(docs/design.md 6.2). Conditional deletion is how field leaks happen; a separate class per principal
can be read, reviewed and tested as a list of exactly what that audience sees.
"""
