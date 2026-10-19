"""ForgeRCA application package.

Layering rules (see docs/architecture.md):

- ``ingestion`` turns source documents into evidence anchors. It must not
  import ``api`` and must not open HTTP requests.
- ``retrieval`` turns a query into ranked, de-duplicated evidence IDs.
- ``db`` owns persistence and migrations only.
- ``api`` is the HTTP boundary: request validation and response shaping.
  Routes call into the other layers; they do not contain retrieval, parsing
  or persistence logic themselves.
- ``schemas`` holds shared data contracts that every other layer may import.

Dependencies point inward: ``api`` may import anything, ``schemas`` may be
imported by anything, and no layer imports ``api``. ``tests/test_app_layers.py``
enforces this direction as code arrives.
"""
