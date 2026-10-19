"""HTTP boundary: request validation, orchestration call and response shaping.

Filled at M4-18 with ``POST /diagnoses``; M1 has no HTTP service. Routes stay
thin: they validate input, delegate to the other layers and shape responses.
Parsing, retrieval and SQL logic must not live in a route handler.

No other layer imports ``app.api``; that direction is enforced by
``tests/test_app_layers.py``.
"""
