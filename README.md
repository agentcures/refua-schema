# refua-schema

`refua-schema` is a portfolio-centric object model for the Refua ecosystem.
It starts with `Portfolio`, nests `Disease`, then `Rationale`, then `Drug`, and
reuses canonical scientific and workflow objects from sibling Refua packages
instead of redefining parallel versions.

## What it provides

- A top-level object hierarchy for discovery portfolios:
  `Portfolio -> Disease -> Rationale -> Drug`.
- Reuse of core `refua` entities such as `Protein`, `SmallMolecule`, `Binder`,
  `Complex`, `DNA`, and `RNA`.
- Reuse of downstream workflow objects from:
  - `refua-clinical` for `SimulationConfig` and `TrialSimulationResult`
  - `refua-preclinical` for `PreclinicalStudySpec`
  - `refua-regulatory` for bundle and provenance records
- Domain metadata objects that fit drug discovery naturally:
  `Evidence`, `Biomarker`, `Assay`, `Modality`, `AdmetProfile`, and
  `ClinicalTrial`.
- JSON/YAML round-tripping for portfolios that preserve nested Refua object
  types.

## Install

```bash
cd refua-schema
pip install -e .
```

With development tooling:

```bash
poetry install -E dev
```

With optional SQLModel persistence support:

```bash
poetry install -E sqlmodel
```

With both:

```bash
poetry install -E dev -E sqlmodel
```

## Quickstart

```python
from pathlib import Path

from refua import Complex, Protein, SmallMolecule
from refua_clinical.models import default_simulation_config
from refua_preclinical.models import default_study_spec
from refua_schema import (
    AdmetProfile,
    Assay,
    Disease,
    Drug,
    Modality,
    Portfolio,
    Rationale,
)

egfr = Protein(sequence="LEEKKGNYVVTDHAFV...", ids="A")
lead = SmallMolecule.from_smiles("CCOc1ccc(NC(=O)N2CCN(C)CC2)cc1", name="lead-1")
binding_model = Complex([egfr, lead], name="egfr-lead-1")

trial = default_simulation_config()
trial.trial_id = "egfr-phase2"
trial.indication = "Non-small cell lung cancer"

tox = default_study_spec()
tox.study_id = "egfr-28d-tox"
tox.indication = "Oncology"

portfolio = Portfolio(portfolio_id="solid-tumors", name="Solid Tumor Portfolio")
portfolio.add_disease(
    Disease(
        disease_id="nsclc",
        name="Non-small cell lung cancer",
        rationales=[
            Rationale(
                rationale_id="egfr-driver",
                title="EGFR oncogenic signaling",
                hypothesis="EGFR-driven tumors remain vulnerable to selective kinase blockade.",
                proteins=[egfr],
                refua_objects=[binding_model],
                drugs=[
                    Drug(
                        drug_id="lead-1",
                        name="Lead 1",
                        modality=Modality(name="oral small molecule", kind="small_molecule", route="oral"),
                        mechanism_of_action="Selective EGFR inhibition",
                        structures=[lead],
                        admet_profiles=[
                            AdmetProfile(
                                profile_id="lead-1-admet",
                                source="txgemma",
                                smiles="CCOc1ccc(NC(=O)N2CCN(C)CC2)cc1",
                                summary_scores={"admet_score": 0.72, "safety_score": 0.68},
                                endpoint_scores={"score_hERG": 0.61, "score_DILI": 0.70},
                            )
                        ],
                        assays=[
                            Assay(
                                assay_id="egfr-biochem",
                                name="EGFR biochemical potency",
                                assay_type="biochemical",
                                endpoint="IC50",
                                result_value=14.2,
                                unit="nM",
                            )
                        ],
                        preclinical_studies=[tox],
                        clinical_trials=[],
                    )
                ],
            )
        ],
    )
)

portfolio.save(Path("artifacts/portfolio.yaml"))
round_tripped = Portfolio.load(Path("artifacts/portfolio.yaml"))
assert round_tripped.diseases[0].rationales[0].drugs[0].name == "Lead 1"
```

## SQLModel persistence

`refua-schema` includes an optional SQLModel adapter in
`refua_schema.sqlmodel_support`. It is intentionally thin:

- The canonical source of truth remains the `Portfolio` Pydantic model.
- SQL storage keeps one full serialized portfolio payload.
- Lightweight index tables for diseases, rationales, and drugs make the
  hierarchy queryable without reproducing the entire schema as ORM columns.

Example:

```python
from pathlib import Path

from refua_schema import Disease, Drug, Portfolio, Rationale
from refua_schema.sqlmodel_support import PortfolioStore

portfolio = Portfolio(
    portfolio_id="pf-sql",
    name="SQL Portfolio",
    diseases=[
        Disease(
            disease_id="dis-sql",
            name="SQL Disease",
            rationales=[
                Rationale(
                    rationale_id="rat-sql",
                    title="SQL Rationale",
                    hypothesis="Persist canonical portfolio payloads with a thin relational index.",
                    drugs=[
                        Drug.from_smiles(
                            drug_id="drug-sql",
                            name="SQL Drug",
                            smiles="CCO",
                        )
                    ],
                )
            ],
        )
    ],
)

store = PortfolioStore.sqlite(Path("artifacts/portfolio.sqlite"))
store.create_schema()
store.save(portfolio)

reloaded = store.load("pf-sql")
assert reloaded.to_dict() == portfolio.to_dict()
assert len(store.list_drugs(portfolio_id="pf-sql")) == 1
```

## Validation

- All core schema models use Pydantic validation with field descriptions.
- Assignment validation stays enabled after object creation.
- The package round-trips JSON/YAML payloads while preserving canonical nested
  Refua object types where supported by the serializer.

## Release checks

Typical first-release verification flow:

```bash
poetry check
poetry install -E dev -E sqlmodel
poetry run ruff check src tests
poetry run pytest
poetry build
```

## Design notes

- `Protein`, `SmallMolecule`, and other structural entities stay in `refua`.
- Clinical simulation config/results stay in `refua-clinical`.
- Preclinical study specs stay in `refua-preclinical`.
- Audit and provenance records stay in `refua-regulatory`.
- `refua-schema` owns the portfolio-level composition layer that links them
  together.
- Optional SQL persistence stays in `refua_schema.sqlmodel_support` so the core
  schema does not take a hard dependency on SQLModel.
