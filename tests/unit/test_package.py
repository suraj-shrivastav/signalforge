"""Smoke test: the package is importable and its version metadata is consistent."""

from importlib.metadata import version

import signalforge


def test_package_imports() -> None:
    assert signalforge.__version__


def test_declared_version_matches_installed_metadata() -> None:
    """Catches bumping `__version__` without bumping `pyproject.toml`, or vice versa."""
    assert version("signalforge") == signalforge.__version__
