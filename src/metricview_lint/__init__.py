"""Offline linter for Databricks Unity Catalog metric view YAML."""

__version__ = "0.1.1"

from .core import Diagnostic, Severity, lint_file, lint_text

__all__ = ["Diagnostic", "Severity", "__version__", "lint_file", "lint_text"]
