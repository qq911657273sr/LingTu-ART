"""Schicht 2 — Interpretation der Roh-Metadaten (vendored from FML; reparse/CLI removed)."""

from __future__ import annotations

from .registry import PARSERS, interpret_items
from .types import InterpretedField, Interpretation

__all__ = ["PARSERS", "interpret_items", "Interpretation", "InterpretedField"]
