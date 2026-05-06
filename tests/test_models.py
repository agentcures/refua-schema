from pathlib import Path

import pytest
from refua import Complex, Protein, SmallMolecule
from refua_clinical.models import default_simulation_config
from refua_clinical.object_api import ClinicalStudy
from refua_clinical.trial import simulate_trials
from refua_preclinical.models import default_study_spec
from refua_regulatory.models import ArtifactRef

from refua_schema import (
    AdmetProfile,
    Assay,
    ClinicalTrial,
    Disease,
    Drug,
    Evidence,
    Modality,
    Portfolio,
    Rationale,
    portfolio_from_mapping,
    portfolio_to_mapping,
)


def test_portfolio_hierarchy_reuses_refua_objects() -> None:
    target = Protein(sequence="ACDEFGHIK", ids="A")
    lead = SmallMolecule.from_smiles("CCO", name="lead-1")
    structure_model = Complex([target, lead], name="target-lead")

    tox = default_study_spec()
    tox.study_id = "tox-001"
    tox.title = "Lead 1 repeat-dose tox"
    tox.indication = "Oncology"
    tox.species = "Rat"
    tox.strain = "Sprague-Dawley"

    config = default_simulation_config()
    config.trial_id = "trial-001"
    config.indication = "Oncology"
    config.phase = "Phase I"
    config.replicates = 4
    config.seed = 11
    result = simulate_trials(config)

    drug = Drug.from_smiles(
        drug_id="lead-1",
        name="Lead 1",
        smiles="CCO",
        modality=Modality(name="oral small molecule", kind="small_molecule", route="oral"),
        mechanism_of_action="Target inhibition",
    )
    drug.add_refua_object(structure_model)
    drug.add_preclinical_study(tox)
    drug.add_assay(
        Assay(
            assay_id="assay-001",
            name="Biochemical potency",
            assay_type="biochemical",
            endpoint="IC50",
            result_value=12.5,
            unit="nM",
        )
    )
    drug.add_admet_profile(
        AdmetProfile(
            profile_id="admet-001",
            source="txgemma",
            smiles="CCO",
            summary_scores={"admet_score": 0.71, "safety_score": 0.68},
            endpoint_scores={"score_hERG": 0.63},
        )
    )
    drug.add_clinical_trial(
        ClinicalTrial(
            trial_id="trial-001",
            title="Lead 1 first-in-human",
            phase="Phase I",
            status="planned",
            indication="Oncology",
            simulation_config=config,
            simulation_result=result,
        )
    )
    drug.artifact_refs.append(
        ArtifactRef(
            artifact_id="art-001",
            role="analysis",
            rel_path="artifacts/lead-1/report.json",
            sha256="abc123",
            size_bytes=256,
        )
    )

    rationale = Rationale(
        rationale_id="rat-001",
        title="Target biology",
        hypothesis="The target is disease-driving and chemically tractable.",
        proteins=[target],
        refua_objects=[structure_model],
        drugs=[drug],
    )
    disease = Disease(
        disease_id="dis-001",
        name="Example Disease",
        therapeutic_area="Oncology",
        rationales=[rationale],
    )
    portfolio = Portfolio(
        portfolio_id="pf-001",
        name="Example Portfolio",
        diseases=[disease],
    )

    assert len(portfolio.iter_rationales()) == 1
    assert len(portfolio.iter_drugs()) == 1
    assert portfolio.iter_drugs()[0].clinical_trials[0].simulation_result is not None


def test_portfolio_round_trip_preserves_external_types(tmp_path: Path) -> None:
    protein = Protein(sequence="ACDEFGHIK", ids="A")
    molecule = SmallMolecule.from_smiles("CCO", name="ethanol")
    complex_obj = Complex([protein, molecule], name="demo-complex")

    portfolio = Portfolio(
        portfolio_id="pf-rt",
        name="Round Trip",
        diseases=[
            Disease(
                disease_id="dis-rt",
                name="Round Trip Disease",
                rationales=[
                    Rationale(
                        rationale_id="rat-rt",
                        title="Round Trip Rationale",
                        hypothesis="Round trip nested objects cleanly.",
                        proteins=[protein],
                        refua_objects=[complex_obj],
                        drugs=[
                            Drug.from_smiles(
                                drug_id="drug-rt",
                                name="Round Trip Drug",
                                smiles="CCO",
                            )
                        ],
                    )
                ],
            )
        ],
    )

    payload = portfolio_to_mapping(portfolio)
    restored = portfolio_from_mapping(payload)

    assert isinstance(restored.diseases[0].rationales[0].proteins[0], Protein)
    assert isinstance(restored.diseases[0].rationales[0].refua_objects[0], Complex)
    assert isinstance(restored.diseases[0].rationales[0].drugs[0].structures[0], SmallMolecule)

    out_path = tmp_path / "portfolio.yaml"
    portfolio.save(out_path)
    loaded = Portfolio.load(out_path)
    assert loaded.portfolio_id == "pf-rt"
    assert loaded.diseases[0].rationales[0].drugs[0].name == "Round Trip Drug"


def test_validation_rejects_blank_ids_and_out_of_range_scores() -> None:
    with pytest.raises(ValueError, match="portfolio_id"):
        Portfolio(portfolio_id=" ", name="Example Portfolio")

    with pytest.raises(ValueError, match="confidence_score"):
        Evidence(
            evidence_id="ev-001",
            title="Paper",
            summary="Strong support.",
            confidence_score=1.5,
        )

    with pytest.raises(ValueError, match="summary_scores.admet_score"):
        AdmetProfile(
            profile_id="admet-001",
            source="txgemma",
            summary_scores={"admet_score": -0.1},
        )


def test_assignment_validation_applies_after_object_creation() -> None:
    portfolio = Portfolio(portfolio_id="pf-assign", name="Assignment Validation")

    with pytest.raises(ValueError, match="name"):
        portfolio.name = " "

    evidence = Evidence(
        evidence_id="ev-001",
        title="Initial data package",
        summary="Supports the asset.",
        confidence_score=0.8,
    )
    with pytest.raises(ValueError, match="confidence_score"):
        evidence.confidence_score = 5.0


def test_clinical_trial_round_trip_preserves_refua_clinical_aggregate() -> None:
    run = ClinicalStudy.default().trial(trial_id="schema-rich-trial", replicates=5).simulate()
    refua_trial = run.to_trial(title="Schema Rich Trial")
    schema_trial = ClinicalTrial.from_refua_clinical(refua_trial)

    portfolio = Portfolio(
        portfolio_id="pf-rich",
        name="Rich Clinical Portfolio",
        diseases=[
            Disease(
                disease_id="dis-rich",
                name="Rich Disease",
                rationales=[
                    Rationale(
                        rationale_id="rat-rich",
                        title="Rich Rationale",
                        hypothesis="Clinical aggregate should round-trip.",
                        drugs=[
                            Drug.from_smiles(
                                drug_id="drug-rich",
                                name="Rich Drug",
                                smiles="CCO",
                            ).add_clinical_trial(schema_trial)
                        ],
                    )
                ],
            )
        ],
    )

    restored = portfolio_from_mapping(portfolio_to_mapping(portfolio))
    restored_trial = restored.diseases[0].rationales[0].drugs[0].clinical_trials[0]
    assert restored_trial.clinical_trial is not None
    assert restored_trial.clinical_trial.result is not None
    assert restored_trial.simulation_result is not None
