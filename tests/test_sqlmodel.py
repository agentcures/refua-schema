from pathlib import Path

import pytest

try:
    import sqlmodel

    from refua_schema import Disease, Drug, Evidence, Modality, Portfolio, Rationale
    from refua_schema.sqlmodel_support import (
        PortfolioRecord,
        PortfolioStore,
        create_schema,
        create_sqlite_engine,
        list_disease_records,
        list_drug_records,
        list_portfolio_records,
        list_rationale_records,
    )
except ImportError:  # pragma: no cover
    pytest.skip("sqlmodel extra not installed", allow_module_level=True)

Session = sqlmodel.Session
select = sqlmodel.select


def _sample_portfolio() -> Portfolio:
    return Portfolio(
        portfolio_id="pf-sql",
        name="SQL Portfolio",
        diseases=[
            Disease(
                disease_id="dis-sql",
                name="SQL Disease",
                therapeutic_area="Oncology",
                rationales=[
                    Rationale(
                        rationale_id="rat-sql",
                        title="SQL Rationale",
                        hypothesis="Persistence adapter smoke test.",
                        evidence=[
                            Evidence(
                                evidence_id="ev-sql",
                                title="SQL Evidence",
                                summary="Evidence travels through JSON payload storage.",
                                confidence_score=0.9,
                            )
                        ],
                        drugs=[
                            Drug.from_smiles(
                                drug_id="drug-sql",
                                name="SQL Drug",
                                smiles="CCO",
                                modality=Modality(
                                    name="small molecule",
                                    kind="small_molecule",
                                    route="oral",
                                ),
                            )
                        ],
                    )
                ],
            )
        ],
    )


def test_sqlmodel_round_trip_with_sqlite(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "portfolio.db")
    create_schema(engine)
    store = PortfolioStore(engine)

    original = _sample_portfolio()
    record = store.save(original)

    assert record.portfolio_id == "pf-sql"
    restored = store.load("pf-sql")
    assert restored.to_dict() == original.to_dict()

    with Session(engine) as session:
        portfolio_rows = list_portfolio_records(session)
        disease_rows = list_disease_records(session, portfolio_id="pf-sql")
        rationale_rows = list_rationale_records(session, portfolio_id="pf-sql")
        drug_rows = list_drug_records(session, portfolio_id="pf-sql")

        assert len(portfolio_rows) == 1
        assert len(disease_rows) == 1
        assert len(rationale_rows) == 1
        assert len(drug_rows) == 1
        assert drug_rows[0].modality_kind == "small_molecule"


def test_sqlmodel_replace_refreshes_index_rows(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "replace.db")
    store = PortfolioStore(engine)
    store.create_schema()

    original = _sample_portfolio()
    store.save(original)

    updated = Portfolio(
        portfolio_id="pf-sql",
        name="SQL Portfolio Updated",
        diseases=[
            Disease(
                disease_id="dis-sql-2",
                name="SQL Disease 2",
                rationales=[
                    Rationale(
                        rationale_id="rat-sql-2",
                        title="SQL Rationale 2",
                        hypothesis="Replace should refresh derived rows.",
                        drugs=[
                            Drug.from_smiles(
                                drug_id="drug-sql-2",
                                name="SQL Drug 2",
                                smiles="CCN",
                            )
                        ],
                    )
                ],
            )
        ],
    )
    store.save(updated, replace=True)

    restored = store.load("pf-sql")
    assert restored.name == "SQL Portfolio Updated"
    assert restored.diseases[0].disease_id == "dis-sql-2"

    with Session(engine) as session:
        assert len(list(session.exec(select(PortfolioRecord)))) == 1
        assert len(store.list_diseases(portfolio_id="pf-sql")) == 1
        assert store.list_diseases(portfolio_id="pf-sql")[0].disease_id == "dis-sql-2"
