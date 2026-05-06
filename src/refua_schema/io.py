"""Serialization helpers for refua-schema.

The helpers in this module are intentionally explicit rather than relying on
generic JSON serialization. The schema contains a mix of Pydantic models and
canonical external Refua dataclasses/classes, so round-trip behavior is made
deterministic by preserving type tags for non-schema objects.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import yaml
from rdkit import Chem
from refua import DNA, RNA, AntibodyBinders, Binder, Complex, Protein, SmallMolecule
from refua_clinical.io import (
    clinical_trial_from_mapping,
    clinical_trial_to_mapping,
    config_from_mapping,
    config_to_mapping,
)
from refua_clinical.models import (
    ClinicalTrial as RefuaClinicalTrial,
)
from refua_clinical.models import (
    InterimUpdate,
    ReplicateResult,
    SimulationConfig,
    TrialSimulationResult,
)
from refua_clinical.trial import trial_result_to_mapping
from refua_preclinical.models import (
    PreclinicalStudySpec,
    study_spec_from_mapping,
    study_spec_to_mapping,
)
from refua_regulatory.models import (
    ArtifactRef,
    DataProvenance,
    DecisionRecord,
    EvidenceBundleManifest,
    ExecutionProvenance,
    ModelProvenance,
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
    SchemaRoot,
)

_TYPE_KEY = "__type__"


def load_mapping(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    raw = file_path.read_text(encoding="utf-8")
    if file_path.suffix.lower() == ".json":
        payload = json.loads(raw)
    else:
        parsed = yaml.safe_load(raw)
        payload = {} if parsed is None else parsed
    if not isinstance(payload, dict):
        raise ValueError(f"Top-level document must be an object: {file_path}")
    return dict(payload)


def dump_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump_yaml(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def dump_portfolio(path: str | Path, portfolio: Portfolio) -> None:
    payload = portfolio_to_mapping(portfolio)
    out = Path(path)
    if out.suffix.lower() == ".json":
        dump_json(out, payload)
        return
    dump_yaml(out, payload)


def load_portfolio(path: str | Path) -> Portfolio:
    return portfolio_from_mapping(load_mapping(path))


def schema_to_mapping(node: SchemaRoot) -> dict[str, Any]:
    return cast(dict[str, Any], _serialize(node))


def portfolio_to_mapping(portfolio: Portfolio) -> dict[str, Any]:
    return schema_to_mapping(portfolio)


def portfolio_from_mapping(data: Mapping[str, Any]) -> Portfolio:
    return _portfolio_from_mapping(_mapping(data))


def _serialize(value: Any) -> Any:
    if isinstance(value, Portfolio):
        return {
            "portfolio_id": value.portfolio_id,
            "name": value.name,
            "owner": value.owner,
            "strategy": value.strategy,
            "diseases": [_serialize(item) for item in value.diseases],
            "metadata": _serialize(value.metadata),
        }
    if isinstance(value, Disease):
        return {
            "disease_id": value.disease_id,
            "name": value.name,
            "therapeutic_area": value.therapeutic_area,
            "stage": value.stage,
            "biomarkers": [_serialize(item) for item in value.biomarkers],
            "evidence": [_serialize(item) for item in value.evidence],
            "rationales": [_serialize(item) for item in value.rationales],
            "metadata": _serialize(value.metadata),
        }
    if isinstance(value, Rationale):
        return {
            "rationale_id": value.rationale_id,
            "title": value.title,
            "hypothesis": value.hypothesis,
            "mechanism": value.mechanism,
            "proteins": [_serialize(item) for item in value.proteins],
            "refua_objects": [_serialize(item) for item in value.refua_objects],
            "biomarkers": [_serialize(item) for item in value.biomarkers],
            "evidence": [_serialize(item) for item in value.evidence],
            "assays": [_serialize(item) for item in value.assays],
            "drugs": [_serialize(item) for item in value.drugs],
            "metadata": _serialize(value.metadata),
        }
    if isinstance(value, Drug):
        return {
            "drug_id": value.drug_id,
            "name": value.name,
            "modality": _serialize(value.modality),
            "mechanism_of_action": value.mechanism_of_action,
            "structures": [_serialize(item) for item in value.structures],
            "refua_objects": [_serialize(item) for item in value.refua_objects],
            "admet_profiles": [_serialize(item) for item in value.admet_profiles],
            "assays": [_serialize(item) for item in value.assays],
            "biomarkers": [_serialize(item) for item in value.biomarkers],
            "evidence": [_serialize(item) for item in value.evidence],
            "preclinical_studies": [_serialize(item) for item in value.preclinical_studies],
            "clinical_trials": [_serialize(item) for item in value.clinical_trials],
            "artifact_refs": [_serialize(item) for item in value.artifact_refs],
            "evidence_bundles": [_serialize(item) for item in value.evidence_bundles],
            "decision_records": [_serialize(item) for item in value.decision_records],
            "data_provenance": [_serialize(item) for item in value.data_provenance],
            "model_provenance": [_serialize(item) for item in value.model_provenance],
            "metadata": _serialize(value.metadata),
        }
    if isinstance(value, ClinicalTrial):
        return {
            "trial_id": value.trial_id,
            "title": value.title,
            "phase": value.phase,
            "status": value.status,
            "indication": value.indication,
            "sponsor": value.sponsor,
            "registry_id": value.registry_id,
            "simulation_config": _serialize(value.simulation_config),
            "simulation_result": _serialize(value.simulation_result),
            "clinical_trial": _serialize(value.clinical_trial),
            "metadata": _serialize(value.metadata),
        }
    if isinstance(value, Evidence | Biomarker | Assay | Modality | AdmetProfile):
        return {key: _serialize(item) for key, item in value.model_dump(mode="python").items()}

    if isinstance(value, Protein):
        return {
            _TYPE_KEY: "Protein",
            "sequence": value.sequence,
            "ids": value.ids,
            "modifications": list(value.modifications),
            "msa": value.msa,
            "binding_types": value.binding_types,
            "secondary_structure": value.secondary_structure,
            "cyclic": value.cyclic,
        }
    if isinstance(value, DNA):
        return {_TYPE_KEY: "DNA", **asdict(value)}
    if isinstance(value, RNA):
        return {_TYPE_KEY: "RNA", **asdict(value)}
    if isinstance(value, Binder):
        return {_TYPE_KEY: "Binder", **asdict(value)}
    if isinstance(value, AntibodyBinders):
        return {
            _TYPE_KEY: "AntibodyBinders",
            "heavy": _serialize(value.heavy),
            "light": _serialize(value.light),
        }
    if isinstance(value, SmallMolecule):
        return {
            _TYPE_KEY: "SmallMolecule",
            "name": value.name,
            "smiles": Chem.MolToSmiles(value.mol, canonical=True),
        }
    if isinstance(value, Complex):
        return {
            _TYPE_KEY: "Complex",
            "name": value.name,
            "base_dir": str(value.base_dir) if value.base_dir is not None else None,
            "entities": [_serialize(item) for item in value.entities],
        }
    if isinstance(value, SimulationConfig):
        return {_TYPE_KEY: "SimulationConfig", **config_to_mapping(value)}
    if isinstance(value, TrialSimulationResult):
        return {_TYPE_KEY: "TrialSimulationResult", **trial_result_to_mapping(value)}
    if isinstance(value, RefuaClinicalTrial):
        return {_TYPE_KEY: "RefuaClinicalTrial", **clinical_trial_to_mapping(value)}
    if isinstance(value, PreclinicalStudySpec):
        return {_TYPE_KEY: "PreclinicalStudySpec", **study_spec_to_mapping(value)}
    if isinstance(value, ArtifactRef):
        return {_TYPE_KEY: "ArtifactRef", **asdict(value)}
    if isinstance(value, ModelProvenance):
        return {_TYPE_KEY: "ModelProvenance", **asdict(value)}
    if isinstance(value, DataProvenance):
        return {_TYPE_KEY: "DataProvenance", **asdict(value)}
    if isinstance(value, DecisionRecord):
        return {_TYPE_KEY: "DecisionRecord", **asdict(value)}
    if isinstance(value, ExecutionProvenance):
        return {_TYPE_KEY: "ExecutionProvenance", **asdict(value)}
    if isinstance(value, EvidenceBundleManifest):
        return {
            _TYPE_KEY: "EvidenceBundleManifest",
            "schema_version": value.schema_version,
            "bundle_id": value.bundle_id,
            "created_at": value.created_at,
            "campaign_run_id": value.campaign_run_id,
            "source_kind": value.source_kind,
            "source_rel_path": value.source_rel_path,
            "decision_count": value.decision_count,
            "artifact_count": value.artifact_count,
            "model_count": value.model_count,
            "data_count": value.data_count,
            "files": list(value.files),
            "model_provenance": [_serialize(item) for item in value.model_provenance],
            "data_provenance": [_serialize(item) for item in value.data_provenance],
            "execution_provenance": _serialize(value.execution_provenance),
            "checklist_reports": list(value.checklist_reports),
            "checklist_summary": _serialize(value.checklist_summary),
            "warnings": list(value.warnings),
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list | tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


def _portfolio_from_mapping(data: Mapping[str, Any]) -> Portfolio:
    return Portfolio(
        portfolio_id=_required_str(data, "portfolio_id"),
        name=_required_str(data, "name"),
        owner=_optional_str(data.get("owner")),
        strategy=_optional_str(data.get("strategy")),
        diseases=[_disease_from_mapping(item) for item in _list_of_mappings(data.get("diseases"))],
        metadata=_mapping(data.get("metadata")),
    )


def _disease_from_mapping(data: Mapping[str, Any]) -> Disease:
    return Disease(
        disease_id=_required_str(data, "disease_id"),
        name=_required_str(data, "name"),
        therapeutic_area=_optional_str(data.get("therapeutic_area")),
        stage=_optional_str(data.get("stage")),
        biomarkers=[_biomarker_from_mapping(item) for item in _list_of_mappings(data.get("biomarkers"))],
        evidence=[_evidence_from_mapping(item) for item in _list_of_mappings(data.get("evidence"))],
        rationales=[_rationale_from_mapping(item) for item in _list_of_mappings(data.get("rationales"))],
        metadata=_mapping(data.get("metadata")),
    )


def _rationale_from_mapping(data: Mapping[str, Any]) -> Rationale:
    return Rationale(
        rationale_id=_required_str(data, "rationale_id"),
        title=_required_str(data, "title"),
        hypothesis=_required_str(data, "hypothesis"),
        mechanism=_optional_str(data.get("mechanism")),
        proteins=[cast(Protein, _external_from_mapping(item)) for item in _list_of_mappings(data.get("proteins"))],
        refua_objects=[_external_from_mapping(item) for item in _list_of_mappings(data.get("refua_objects"))],
        biomarkers=[_biomarker_from_mapping(item) for item in _list_of_mappings(data.get("biomarkers"))],
        evidence=[_evidence_from_mapping(item) for item in _list_of_mappings(data.get("evidence"))],
        assays=[_assay_from_mapping(item) for item in _list_of_mappings(data.get("assays"))],
        drugs=[_drug_from_mapping(item) for item in _list_of_mappings(data.get("drugs"))],
        metadata=_mapping(data.get("metadata")),
    )


def _drug_from_mapping(data: Mapping[str, Any]) -> Drug:
    return Drug(
        drug_id=_required_str(data, "drug_id"),
        name=_required_str(data, "name"),
        modality=_modality_from_mapping(_mapping(data.get("modality"))),
        mechanism_of_action=_optional_str(data.get("mechanism_of_action")),
        structures=[
            cast(SmallMolecule, _external_from_mapping(item))
            for item in _list_of_mappings(data.get("structures"))
        ],
        refua_objects=[_external_from_mapping(item) for item in _list_of_mappings(data.get("refua_objects"))],
        admet_profiles=[_admet_from_mapping(item) for item in _list_of_mappings(data.get("admet_profiles"))],
        assays=[_assay_from_mapping(item) for item in _list_of_mappings(data.get("assays"))],
        biomarkers=[_biomarker_from_mapping(item) for item in _list_of_mappings(data.get("biomarkers"))],
        evidence=[_evidence_from_mapping(item) for item in _list_of_mappings(data.get("evidence"))],
        preclinical_studies=[
            cast(PreclinicalStudySpec, _external_from_mapping(item))
            for item in _list_of_mappings(data.get("preclinical_studies"))
        ],
        clinical_trials=[
            _clinical_trial_from_mapping(item)
            for item in _list_of_mappings(data.get("clinical_trials"))
        ],
        artifact_refs=[
            cast(ArtifactRef, _external_from_mapping(item))
            for item in _list_of_mappings(data.get("artifact_refs"))
        ],
        evidence_bundles=[
            cast(EvidenceBundleManifest, _external_from_mapping(item))
            for item in _list_of_mappings(data.get("evidence_bundles"))
        ],
        decision_records=[
            cast(DecisionRecord, _external_from_mapping(item))
            for item in _list_of_mappings(data.get("decision_records"))
        ],
        data_provenance=[
            cast(DataProvenance, _external_from_mapping(item))
            for item in _list_of_mappings(data.get("data_provenance"))
        ],
        model_provenance=[
            cast(ModelProvenance, _external_from_mapping(item))
            for item in _list_of_mappings(data.get("model_provenance"))
        ],
        metadata=_mapping(data.get("metadata")),
    )


def _clinical_trial_from_mapping(data: Mapping[str, Any]) -> ClinicalTrial:
    simulation_config_raw = data.get("simulation_config")
    simulation_result_raw = data.get("simulation_result")
    clinical_trial_raw = data.get("clinical_trial")
    return ClinicalTrial(
        trial_id=_required_str(data, "trial_id"),
        title=_required_str(data, "title"),
        phase=_required_str(data, "phase"),
        status=str(data.get("status", "planned")),
        indication=_optional_str(data.get("indication")),
        sponsor=_optional_str(data.get("sponsor")),
        registry_id=_optional_str(data.get("registry_id")),
        simulation_config=(
            cast(SimulationConfig, _external_from_mapping(simulation_config_raw))
            if isinstance(simulation_config_raw, Mapping)
            else None
        ),
        simulation_result=(
            cast(TrialSimulationResult, _external_from_mapping(simulation_result_raw))
            if isinstance(simulation_result_raw, Mapping)
            else None
        ),
        clinical_trial=(
            cast(RefuaClinicalTrial, _external_from_mapping(clinical_trial_raw))
            if isinstance(clinical_trial_raw, Mapping)
            else None
        ),
        metadata=_mapping(data.get("metadata")),
    )


def _evidence_from_mapping(data: Mapping[str, Any]) -> Evidence:
    return Evidence(
        evidence_id=_required_str(data, "evidence_id"),
        title=_required_str(data, "title"),
        summary=_required_str(data, "summary"),
        source_type=str(data.get("source_type", "literature")),
        source=_optional_str(data.get("source")),
        url=_optional_str(data.get("url")),
        confidence_score=_optional_float(data.get("confidence_score")),
        metadata=_mapping(data.get("metadata")),
    )


def _biomarker_from_mapping(data: Mapping[str, Any]) -> Biomarker:
    return Biomarker(
        biomarker_id=_required_str(data, "biomarker_id"),
        name=_required_str(data, "name"),
        role=_required_str(data, "role"),
        value=cast(float | str | None, data.get("value")),
        unit=_optional_str(data.get("unit")),
        direction=_optional_str(data.get("direction")),
        metadata=_mapping(data.get("metadata")),
    )


def _assay_from_mapping(data: Mapping[str, Any]) -> Assay:
    return Assay(
        assay_id=_required_str(data, "assay_id"),
        name=_required_str(data, "name"),
        assay_type=_required_str(data, "assay_type"),
        endpoint=_required_str(data, "endpoint"),
        result_value=cast(float | str | None, data.get("result_value")),
        unit=_optional_str(data.get("unit")),
        system=_optional_str(data.get("system")),
        stage=_optional_str(data.get("stage")),
        metadata=_mapping(data.get("metadata")),
    )


def _modality_from_mapping(data: Mapping[str, Any]) -> Modality:
    return Modality(
        name=_required_str(data, "name"),
        kind=_required_str(data, "kind"),
        route=_optional_str(data.get("route")),
        subtype=_optional_str(data.get("subtype")),
        delivery=_optional_str(data.get("delivery")),
        metadata=_mapping(data.get("metadata")),
    )


def _admet_from_mapping(data: Mapping[str, Any]) -> AdmetProfile:
    return AdmetProfile(
        profile_id=_required_str(data, "profile_id"),
        source=_required_str(data, "source"),
        smiles=_optional_str(data.get("smiles")),
        summary_scores=_float_mapping(data.get("summary_scores")),
        endpoint_scores=_float_mapping(data.get("endpoint_scores")),
        endpoint_calls=_string_mapping(data.get("endpoint_calls")),
        red_flags=_string_list(data.get("red_flags")),
        yellow_flags=_string_list(data.get("yellow_flags")),
        metadata=_mapping(data.get("metadata")),
    )


def _external_from_mapping(raw: Any) -> Any:
    data = _mapping(raw)
    type_name = _required_str(data, _TYPE_KEY)
    payload = dict(data)
    payload.pop(_TYPE_KEY, None)

    if type_name == "Protein":
        return Protein(**payload)
    if type_name == "DNA":
        return DNA(**payload)
    if type_name == "RNA":
        return RNA(**payload)
    if type_name == "Binder":
        return Binder(**payload)
    if type_name == "AntibodyBinders":
        heavy = cast(Binder, _external_from_mapping(payload.get("heavy")))
        light = cast(Binder, _external_from_mapping(payload.get("light")))
        return AntibodyBinders(heavy=heavy, light=light)
    if type_name == "SmallMolecule":
        smiles = _required_str(payload, "smiles")
        name = _optional_str(payload.get("name"))
        return SmallMolecule.from_smiles(smiles, name=name)
    if type_name == "Complex":
        entities = [_external_from_mapping(item) for item in _list_of_mappings(payload.get("entities"))]
        return Complex(
            entities=entities,
            name=str(payload.get("name", "complex")),
            base_dir=_optional_str(payload.get("base_dir")),
        )
    if type_name == "SimulationConfig":
        return config_from_mapping(payload)
    if type_name == "TrialSimulationResult":
        return _trial_result_from_mapping(payload)
    if type_name == "RefuaClinicalTrial":
        return clinical_trial_from_mapping(payload)
    if type_name == "PreclinicalStudySpec":
        return study_spec_from_mapping(payload)
    if type_name == "ArtifactRef":
        return ArtifactRef(
            artifact_id=_required_str(payload, "artifact_id"),
            role=_required_str(payload, "role"),
            rel_path=_required_str(payload, "rel_path"),
            sha256=_required_str(payload, "sha256"),
            size_bytes=int(payload.get("size_bytes", 0)),
            media_type=_optional_str(payload.get("media_type")),
            metadata=_mapping(payload.get("metadata")),
        )
    if type_name == "ModelProvenance":
        return ModelProvenance(
            model_name=_required_str(payload, "model_name"),
            model_version=_optional_str(payload.get("model_version")),
            tool=_optional_str(payload.get("tool")),
            backend=_optional_str(payload.get("backend")),
            parameters=_mapping(payload.get("parameters")),
        )
    if type_name == "DataProvenance":
        return DataProvenance(
            dataset_id=_required_str(payload, "dataset_id"),
            version=_optional_str(payload.get("version")),
            source_url=_optional_str(payload.get("source_url")),
            sha256=_optional_str(payload.get("sha256")),
            license_name=_optional_str(payload.get("license_name")),
            manifest_rel_path=_optional_str(payload.get("manifest_rel_path")),
            metadata=_mapping(payload.get("metadata")),
        )
    if type_name == "DecisionRecord":
        return DecisionRecord(
            decision_id=_required_str(payload, "decision_id"),
            campaign_run_id=_required_str(payload, "campaign_run_id"),
            step_index=int(payload.get("step_index", 0)),
            timestamp=_required_str(payload, "timestamp"),
            decision_type=_required_str(payload, "decision_type"),
            actor=_required_str(payload, "actor"),
            rationale=_required_str(payload, "rationale"),
            tool=_optional_str(payload.get("tool")),
            args=_mapping(payload.get("args")),
            output_preview=_optional_str(payload.get("output_preview")),
            input_refs=tuple(_string_list(payload.get("input_refs"))),
            output_refs=tuple(_string_list(payload.get("output_refs"))),
            metadata=_mapping(payload.get("metadata")),
        )
    if type_name == "ExecutionProvenance":
        return ExecutionProvenance(
            captured_at=_required_str(payload, "captured_at"),
            runtime=_mapping(payload.get("runtime")),
            git=_mapping(payload.get("git")),
            dependencies=_string_mapping(payload.get("dependencies")),
            extra=_mapping(payload.get("extra")),
        )
    if type_name == "EvidenceBundleManifest":
        execution_raw = payload.get("execution_provenance")
        return EvidenceBundleManifest(
            schema_version=_required_str(payload, "schema_version"),
            bundle_id=_required_str(payload, "bundle_id"),
            created_at=_required_str(payload, "created_at"),
            campaign_run_id=_required_str(payload, "campaign_run_id"),
            source_kind=_required_str(payload, "source_kind"),
            source_rel_path=_required_str(payload, "source_rel_path"),
            decision_count=int(payload.get("decision_count", 0)),
            artifact_count=int(payload.get("artifact_count", 0)),
            model_count=int(payload.get("model_count", 0)),
            data_count=int(payload.get("data_count", 0)),
            files=tuple(_string_list(payload.get("files"))),
            model_provenance=tuple(
                cast(ModelProvenance, _external_from_mapping(item))
                for item in _list_of_mappings(payload.get("model_provenance"))
            ),
            data_provenance=tuple(
                cast(DataProvenance, _external_from_mapping(item))
                for item in _list_of_mappings(payload.get("data_provenance"))
            ),
            execution_provenance=(
                cast(ExecutionProvenance, _external_from_mapping(execution_raw))
                if isinstance(execution_raw, Mapping)
                else None
            ),
            checklist_reports=tuple(_string_list(payload.get("checklist_reports"))),
            checklist_summary=_mapping(payload.get("checklist_summary")),
            warnings=tuple(_string_list(payload.get("warnings"))),
        )
    raise ValueError(f"Unsupported serialized external object type: {type_name}")


def _trial_result_from_mapping(data: Mapping[str, Any]) -> TrialSimulationResult:
    config = config_from_mapping(_mapping(data.get("config")))
    replicate_rows = data.get("replicates")
    if not isinstance(replicate_rows, list):
        raise ValueError("TrialSimulationResult.replicates must be a list")
    replicates: list[ReplicateResult] = []
    for item in replicate_rows:
        row = _mapping(item)
        allocation_trace = [
            InterimUpdate(
                enrolled_n=int(_mapping(update).get("enrolled_n", 0)),
                allocation=_float_mapping(_mapping(update).get("allocation")),
                posterior_best_probability=_float_mapping(
                    _mapping(update).get("posterior_best_probability")
                ),
            )
            for update in _list_of_mappings(row.get("allocation_trace"))
        ]
        replicates.append(
            ReplicateResult(
                replicate_id=int(row.get("replicate_id", 0)),
                treatment_effect=float(row.get("treatment_effect", 0.0)),
                p_value=float(row.get("p_value", 1.0)),
                achieved_target=bool(row.get("achieved_target", False)),
                responders_treatment=float(row.get("responders_treatment", 0.0)),
                responders_control=float(row.get("responders_control", 0.0)),
                safety_event_rate=float(row.get("safety_event_rate", 0.0)),
                enrolled_n=int(row.get("enrolled_n", 0)),
                stop_reason=_optional_str(row.get("stop_reason")),
                stop_interim_index=(
                    int(row["stop_interim_index"])
                    if row.get("stop_interim_index") is not None
                    else None
                ),
                effective_external_weight=float(row.get("effective_external_weight", 0.0)),
                decision_cards=[
                    _mapping(card) for card in row.get("decision_cards", [])
                    if isinstance(card, Mapping)
                ],
                allocation_trace=allocation_trace,
                event_rate=_optional_float(row.get("event_rate")),
                active_arm_ids=_string_list(row.get("active_arm_ids")),
                dropped_arm_ids=_string_list(row.get("dropped_arm_ids")),
                arm_enrollment_counts={
                    str(key): int(value)
                    for key, value in _mapping(row.get("arm_enrollment_counts")).items()
                },
                analysis_method=_optional_str(row.get("analysis_method")),
                effect_measure=_optional_str(row.get("effect_measure")),
                effect_raw=_optional_float(row.get("effect_raw")),
            )
        )
    return TrialSimulationResult(
        run_id=_required_str(data, "run_id"),
        config=config,
        summary=_mapping(data.get("summary")),
        replicates=replicates,
    )


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            rows.append(_mapping(item))
    return rows


def _required_str(data: Mapping[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"{field_name} must be a non-empty string")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _float_mapping(value: Any) -> dict[str, float]:
    return {str(key): float(item) for key, item in _mapping(value).items()}


def _string_mapping(value: Any) -> dict[str, str]:
    return {str(key): str(item) for key, item in _mapping(value).items()}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
