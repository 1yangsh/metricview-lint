"""Importing this package registers every rule."""

from . import expressions, formats, joins, materialization, structure, windows

__all__ = ["expressions", "formats", "joins", "materialization", "structure", "windows"]
