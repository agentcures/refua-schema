"""Optional SQLModel persistence support for refua-schema.

This module is intentionally separate from the core schema models so projects
that only need the in-memory Pydantic hierarchy do not take a hard dependency
on SQLAlchemy or SQLModel.

Design
------
- The canonical source of truth remains the core ``Portfolio`` Pydantic model.
- SQLModel tables store one full serialized portfolio payload plus lightweight
  index rows for diseases, rationales, and drugs.
- The adapter avoids reproducing the full schema field graph in ORM tables while
  still making the hierarchy queryable in relational storage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from sqlalchemy import Column
    from sqlalchemy.types import JSON
    from sqlmodel import Field, Session, SQLModel, create_engine, delete, select
except ImportError as exc:  # pragma: no cover - exercised by import boundary only
    msg = (
        "SQLModel support is optional. Install it with "
        "`pip install refua-schema[sqlmodel]` or `poetry install -E sqlmodel`."
    )
    raise ImportError(msg) from exc

from .io import portfolio_from_mapping
from .models import Portfolio


def _disease_key(*, portfolio_id: str, disease_id: str) -> str:
    return f"{portfolio_id}:disease:{disease_id}"


def _rationale_key(
    *,
    portfolio_id: str,
    disease_id: str,
    rationale_id: str,
) -> str:
    return f"{portfolio_id}:disease:{disease_id}:rationale:{rationale_id}"


def _drug_key(
    *,
    portfolio_id: str,
    disease_id: str,
    rationale_id: str,
    drug_id: str,
) -> str:
    return f"{portfolio_id}:disease:{disease_id}:rationale:{rationale_id}:drug:{drug_id}"


class PortfolioRecord(SQLModel, table=True):
    """Relational record storing the canonical serialized portfolio payload."""

    __tablename__ = "portfolio"

    portfolio_id: str = Field(
        primary_key=True,
        description="Stable portfolio identifier.",
    )
    name: str = Field(
        index=True,
        description="Human-readable portfolio name.",
    )
    owner: str | None = Field(
        default=None,
        description="Optional owner stored redundantly for fast filtering.",
    )
    strategy: str | None = Field(
        default=None,
        description="Optional strategy statement stored redundantly for fast filtering.",
    )
    payload: dict[str, Any] = Field(
        sa_column=Column(JSON, nullable=False),
        description="Canonical serialized Portfolio payload.",
    )


class DiseaseRecord(SQLModel, table=True):
    """Relational index row for a disease nested under a portfolio."""

    __tablename__ = "portfolio_disease"

    disease_key: str = Field(
        primary_key=True,
        description="Derived stable relational key for the disease row.",
    )
    portfolio_id: str = Field(
        foreign_key="portfolio.portfolio_id",
        index=True,
        description="Parent portfolio identifier.",
    )
    disease_id: str = Field(
        index=True,
        description="Canonical disease identifier from the schema model.",
    )
    name: str = Field(
        index=True,
        description="Disease display name.",
    )
    therapeutic_area: str | None = Field(
        default=None,
        description="Optional therapeutic area copied from the core disease model.",
    )
    stage: str | None = Field(
        default=None,
        description="Optional portfolio stage copied from the core disease model.",
    )


class RationaleRecord(SQLModel, table=True):
    """Relational index row for a rationale nested under a disease."""

    __tablename__ = "portfolio_rationale"

    rationale_key: str = Field(
        primary_key=True,
        description="Derived stable relational key for the rationale row.",
    )
    disease_key: str = Field(
        foreign_key="portfolio_disease.disease_key",
        index=True,
        description="Parent disease relational key.",
    )
    portfolio_id: str = Field(
        foreign_key="portfolio.portfolio_id",
        index=True,
        description="Owning portfolio identifier for efficient filtering.",
    )
    disease_id: str = Field(
        index=True,
        description="Parent disease identifier from the schema model.",
    )
    rationale_id: str = Field(
        index=True,
        description="Canonical rationale identifier from the schema model.",
    )
    title: str = Field(
        index=True,
        description="Rationale title.",
    )


class DrugRecord(SQLModel, table=True):
    """Relational index row for a drug nested under a rationale."""

    __tablename__ = "portfolio_drug"

    drug_key: str = Field(
        primary_key=True,
        description="Derived stable relational key for the drug row.",
    )
    rationale_key: str = Field(
        foreign_key="portfolio_rationale.rationale_key",
        index=True,
        description="Parent rationale relational key.",
    )
    portfolio_id: str = Field(
        foreign_key="portfolio.portfolio_id",
        index=True,
        description="Owning portfolio identifier for efficient filtering.",
    )
    disease_id: str = Field(
        index=True,
        description="Parent disease identifier from the schema model.",
    )
    rationale_id: str = Field(
        index=True,
        description="Parent rationale identifier from the schema model.",
    )
    drug_id: str = Field(
        index=True,
        description="Canonical drug identifier from the schema model.",
    )
    name: str = Field(
        index=True,
        description="Drug display name.",
    )
    modality_kind: str | None = Field(
        default=None,
        index=True,
        description="Normalized modality kind copied from the core drug model.",
    )


def create_sqlite_engine(
    path: str | Path = ":memory:",
    *,
    echo: bool = False,
):
    """Create a SQLite engine for SQLModel-backed schema persistence."""
    if str(path) == ":memory:":
        url = "sqlite://"
    else:
        resolved = Path(path).expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{resolved}"
    return create_engine(url, echo=echo)


def create_schema(engine: Any) -> None:
    """Create all SQLModel tables required by the persistence adapter."""
    SQLModel.metadata.create_all(engine)


def drop_schema(engine: Any) -> None:
    """Drop all SQLModel tables managed by the persistence adapter."""
    SQLModel.metadata.drop_all(engine)


def _portfolio_record_from_model(portfolio: Portfolio) -> PortfolioRecord:
    return PortfolioRecord(
        portfolio_id=portfolio.portfolio_id,
        name=portfolio.name,
        owner=portfolio.owner,
        strategy=portfolio.strategy,
        payload=portfolio.to_dict(),
    )


def _disease_records_from_model(portfolio: Portfolio) -> list[DiseaseRecord]:
    return [
        DiseaseRecord(
            disease_key=_disease_key(
                portfolio_id=portfolio.portfolio_id,
                disease_id=disease.disease_id,
            ),
            portfolio_id=portfolio.portfolio_id,
            disease_id=disease.disease_id,
            name=disease.name,
            therapeutic_area=disease.therapeutic_area,
            stage=disease.stage,
        )
        for disease in portfolio.diseases
    ]


def _rationale_records_from_model(portfolio: Portfolio) -> list[RationaleRecord]:
    rows: list[RationaleRecord] = []
    for disease in portfolio.diseases:
        disease_key = _disease_key(
            portfolio_id=portfolio.portfolio_id,
            disease_id=disease.disease_id,
        )
        for rationale in disease.rationales:
            rows.append(
                RationaleRecord(
                    rationale_key=_rationale_key(
                        portfolio_id=portfolio.portfolio_id,
                        disease_id=disease.disease_id,
                        rationale_id=rationale.rationale_id,
                    ),
                    disease_key=disease_key,
                    portfolio_id=portfolio.portfolio_id,
                    disease_id=disease.disease_id,
                    rationale_id=rationale.rationale_id,
                    title=rationale.title,
                )
            )
    return rows


def _drug_records_from_model(portfolio: Portfolio) -> list[DrugRecord]:
    rows: list[DrugRecord] = []
    for disease in portfolio.diseases:
        for rationale in disease.rationales:
            rationale_key = _rationale_key(
                portfolio_id=portfolio.portfolio_id,
                disease_id=disease.disease_id,
                rationale_id=rationale.rationale_id,
            )
            for drug in rationale.drugs:
                rows.append(
                    DrugRecord(
                        drug_key=_drug_key(
                            portfolio_id=portfolio.portfolio_id,
                            disease_id=disease.disease_id,
                            rationale_id=rationale.rationale_id,
                            drug_id=drug.drug_id,
                        ),
                        rationale_key=rationale_key,
                        portfolio_id=portfolio.portfolio_id,
                        disease_id=disease.disease_id,
                        rationale_id=rationale.rationale_id,
                        drug_id=drug.drug_id,
                        name=drug.name,
                        modality_kind=drug.modality.kind,
                    )
                )
    return rows


def _delete_existing_portfolio_rows(session: Session, portfolio_id: str) -> None:
    session.exec(delete(DrugRecord).where(DrugRecord.portfolio_id == portfolio_id))
    session.exec(delete(RationaleRecord).where(RationaleRecord.portfolio_id == portfolio_id))
    session.exec(delete(DiseaseRecord).where(DiseaseRecord.portfolio_id == portfolio_id))
    session.exec(delete(PortfolioRecord).where(PortfolioRecord.portfolio_id == portfolio_id))


def save_portfolio(
    session: Session,
    portfolio: Portfolio,
    *,
    replace: bool = True,
) -> PortfolioRecord:
    """Persist a portfolio and refresh its hierarchy index rows.

    Parameters
    ----------
    session
        Active SQLModel session.
    portfolio
        Canonical validated portfolio model to persist.
    replace
        When true, any existing record for the same ``portfolio_id`` is removed
        and rebuilt from the canonical payload and derived index rows.
    """
    if replace:
        _delete_existing_portfolio_rows(session, portfolio.portfolio_id)
    record = _portfolio_record_from_model(portfolio)
    session.add(record)
    for row in _disease_records_from_model(portfolio):
        session.add(row)
    for row in _rationale_records_from_model(portfolio):
        session.add(row)
    for row in _drug_records_from_model(portfolio):
        session.add(row)
    session.commit()
    session.refresh(record)
    return record


def load_portfolio(session: Session, portfolio_id: str) -> Portfolio:
    """Load a canonical portfolio from the relational store."""
    record = session.get(PortfolioRecord, portfolio_id)
    if record is None:
        raise KeyError(f"Portfolio not found: {portfolio_id}")
    return portfolio_from_mapping(record.payload)


def list_portfolio_records(session: Session) -> list[PortfolioRecord]:
    """Return all stored portfolio root records."""
    statement = select(PortfolioRecord).order_by(PortfolioRecord.portfolio_id)
    return list(session.exec(statement))


def list_disease_records(
    session: Session,
    *,
    portfolio_id: str | None = None,
) -> list[DiseaseRecord]:
    """Return disease index rows, optionally filtered by portfolio."""
    statement = select(DiseaseRecord).order_by(
        DiseaseRecord.portfolio_id,
        DiseaseRecord.disease_id,
    )
    if portfolio_id is not None:
        statement = statement.where(DiseaseRecord.portfolio_id == portfolio_id)
    return list(session.exec(statement))


def list_rationale_records(
    session: Session,
    *,
    portfolio_id: str | None = None,
) -> list[RationaleRecord]:
    """Return rationale index rows, optionally filtered by portfolio."""
    statement = select(RationaleRecord).order_by(
        RationaleRecord.portfolio_id,
        RationaleRecord.disease_id,
        RationaleRecord.rationale_id,
    )
    if portfolio_id is not None:
        statement = statement.where(RationaleRecord.portfolio_id == portfolio_id)
    return list(session.exec(statement))


def list_drug_records(
    session: Session,
    *,
    portfolio_id: str | None = None,
) -> list[DrugRecord]:
    """Return drug index rows, optionally filtered by portfolio."""
    statement = select(DrugRecord).order_by(
        DrugRecord.portfolio_id,
        DrugRecord.disease_id,
        DrugRecord.rationale_id,
        DrugRecord.drug_id,
    )
    if portfolio_id is not None:
        statement = statement.where(DrugRecord.portfolio_id == portfolio_id)
    return list(session.exec(statement))


class PortfolioStore:
    """Thin repository wrapper around the SQLModel persistence adapter."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    @classmethod
    def sqlite(
        cls,
        path: str | Path = ":memory:",
        *,
        echo: bool = False,
    ) -> PortfolioStore:
        """Create a SQLite-backed store."""
        return cls(create_sqlite_engine(path, echo=echo))

    def create_schema(self) -> None:
        """Create the SQLModel tables backing the store."""
        create_schema(self.engine)

    def drop_schema(self) -> None:
        """Drop the SQLModel tables backing the store."""
        drop_schema(self.engine)

    def save(self, portfolio: Portfolio, *, replace: bool = True) -> PortfolioRecord:
        """Persist a canonical portfolio in a fresh session."""
        with Session(self.engine) as session:
            return save_portfolio(session, portfolio, replace=replace)

    def load(self, portfolio_id: str) -> Portfolio:
        """Load a canonical portfolio in a fresh session."""
        with Session(self.engine) as session:
            return load_portfolio(session, portfolio_id)

    def list_portfolios(self) -> list[PortfolioRecord]:
        """List stored portfolio root rows."""
        with Session(self.engine) as session:
            return list_portfolio_records(session)

    def list_diseases(self, *, portfolio_id: str | None = None) -> list[DiseaseRecord]:
        """List stored disease index rows."""
        with Session(self.engine) as session:
            return list_disease_records(session, portfolio_id=portfolio_id)

    def list_rationales(
        self,
        *,
        portfolio_id: str | None = None,
    ) -> list[RationaleRecord]:
        """List stored rationale index rows."""
        with Session(self.engine) as session:
            return list_rationale_records(session, portfolio_id=portfolio_id)

    def list_drugs(self, *, portfolio_id: str | None = None) -> list[DrugRecord]:
        """List stored drug index rows."""
        with Session(self.engine) as session:
            return list_drug_records(session, portfolio_id=portfolio_id)


__all__ = [
    "DiseaseRecord",
    "DrugRecord",
    "PortfolioRecord",
    "PortfolioStore",
    "RationaleRecord",
    "create_schema",
    "create_sqlite_engine",
    "drop_schema",
    "list_disease_records",
    "list_drug_records",
    "list_portfolio_records",
    "list_rationale_records",
    "load_portfolio",
    "save_portfolio",
]
