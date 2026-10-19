"""Layering ratchet for the ``app`` package (M1-02).

The directories exist so later milestones have an agreed home. This test
records the dependency direction before there is enough code to violate it:
no layer imports the HTTP boundary, and ``schemas`` stays free of every
other layer so anything can depend on it.

It is a ratchet, not a proof of design quality: it catches an accidental
``from app.api import ...`` inside ``app.db``, nothing more.
"""

from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
LAYERS = ("ingestion", "retrieval", "db", "api", "schemas")

FORBIDDEN_IMPORTS = {
    "ingestion": ("app.api",),
    "retrieval": ("app.api",),
    "db": ("app.api",),
    "schemas": ("app.api", "app.db", "app.ingestion", "app.retrieval"),
}


def imported_modules(path: Path, package: tuple[str, ...]) -> set[str]:
    """Return absolute module names imported by ``path``, resolving relative imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - node.level + 1]
                parts = tuple(part for part in (node.module or "").split(".") if part)
                target = ".".join(base + parts)
            else:
                target = node.module or ""
            if target:
                modules.add(target)
    return modules


class AppLayeringTests(unittest.TestCase):
    def test_required_layers_exist(self):
        for layer in LAYERS:
            with self.subTest(layer=layer):
                self.assertTrue((APP / layer / "__init__.py").is_file(), f"missing app/{layer}")

    def test_layers_are_importable(self):
        for layer in LAYERS:
            with self.subTest(layer=layer):
                module = importlib.import_module(f"app.{layer}")
                self.assertEqual(module.__name__, f"app.{layer}")

    def test_forbidden_import_direction_is_absent(self):
        for layer, forbidden in FORBIDDEN_IMPORTS.items():
            for path in sorted((APP / layer).rglob("*.py")):
                for module in sorted(imported_modules(path, ("app", layer))):
                    for prefix in forbidden:
                        with self.subTest(file=path.name, layer=layer, module=module):
                            self.assertFalse(
                                module == prefix or module.startswith(prefix + "."),
                                f"{path.relative_to(APP.parent)} imports {module}, forbidden for {layer}",
                            )


if __name__ == "__main__":
    unittest.main()
