"""Public API for refua-schema."""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version
from pathlib import Path

from .io import (
    dump_json,
    dump_portfolio,
    dump_yaml,
    load_mapping,
    load_portfolio,
    portfolio_from_mapping,
    portfolio_to_mapping,
    schema_to_mapping,
)
from .models import (
    AdmetProfile,
    Assay,
    Biomarker,
    ClinicalTrial,
    Disease,
    Drug,
    Evidence,
    Modality,
    Portfolio,
    Rationale,
    RefuaObject,
    SchemaNode,
    SchemaRoot,
)


def _read_version_from_pyproject() -> str | None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject_path.exists():
        return None
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    version = project.get("version")
    if not version:
        return None
    return str(version)


def _resolve_version() -> str:
    try:
        return _distribution_version("refua-schema")
    except PackageNotFoundError:
        local_version = _read_version_from_pyproject()
        if local_version is not None:
            return local_version
        raise


__version__ = _resolve_version()

__all__ = [
    "AdmetProfile",
    "Assay",
    "Biomarker",
    "ClinicalTrial",
    "Disease",
    "Drug",
    "Evidence",
    "Modality",
    "Portfolio",
    "Rationale",
    "RefuaObject",
    "SchemaNode",
    "SchemaRoot",
    "__version__",
    "dump_json",
    "dump_portfolio",
    "dump_yaml",
    "load_mapping",
    "load_portfolio",
    "portfolio_from_mapping",
    "portfolio_to_mapping",
    "schema_to_mapping",
]
