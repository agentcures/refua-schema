"""Portfolio-oriented schema objects for the Refua ecosystem.

The models in this module define the canonical portfolio hierarchy:

``Portfolio -> Disease -> Rationale -> Drug``

Each schema model uses Pydantic validation with rich field descriptions so the
objects can serve both as runtime contracts and as self-documenting schema
definitions for tooling, APIs, and serialized artifacts.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from refua import DNA, RNA, AntibodyBinders, Binder, Complex, Protein, SmallMolecule
from refua_clinical.models import SimulationConfig, TrialSimulationResult
from refua_preclinical.models import PreclinicalStudySpec
from refua_regulatory.models import (
    ArtifactRef,
    DataProvenance,
    DecisionRecord,
    EvidenceBundleManifest,
    ModelProvenance,
)

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
IdentifierStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
MetadataDict = dict[str, Any]
RefuaObject = Protein | DNA | RNA | Binder | AntibodyBinders | SmallMolecule | Complex

_REFUA_OBJECT_TYPES: tuple[type[Any], ...] = (
    Protein,
    DNA,
    RNA,
    Binder,
    AntibodyBinders,
    SmallMolecule,
    Complex,
)


def _validate_probability(value: float, *, field_name: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite.")
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0.")
    return value


def _validate_mapping_keys(mapping: MetadataDict, *, field_name: str) -> MetadataDict:
    normalized: MetadataDict = {}
    for key, item in mapping.items():
        key_text = str(key).strip()
        if not key_text:
            raise ValueError(f"{field_name} cannot contain blank keys.")
        normalized[key_text] = item
    return normalized


def _validate_string_mapping(
    mapping: dict[str, str],
    *,
    field_name: str,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, item in mapping.items():
        key_text = str(key).strip()
        value_text = str(item).strip()
        if not key_text:
            raise ValueError(f"{field_name} cannot contain blank keys.")
        if not value_text:
            raise ValueError(f"{field_name}.{key_text} cannot be blank.")
        normalized[key_text] = value_text
    return normalized


def _validate_probability_mapping(
    mapping: dict[str, float],
    *,
    field_name: str,
) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, item in mapping.items():
        key_text = str(key).strip()
        if not key_text:
            raise ValueError(f"{field_name} cannot contain blank keys.")
        normalized[key_text] = _validate_probability(float(item), field_name=f"{field_name}.{key_text}")
    return normalized


def _validate_string_list(values: list[str], *, field_name: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item).strip()
        if not text:
            raise ValueError(f"{field_name} cannot contain blank entries.")
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _validate_refua_objects(objects: list[RefuaObject], *, field_name: str) -> list[RefuaObject]:
    for item in objects:
        if not isinstance(item, _REFUA_OBJECT_TYPES):
            allowed = ", ".join(cls.__name__ for cls in _REFUA_OBJECT_TYPES)
            raise TypeError(f"{field_name} entries must be Refua objects. Allowed: {allowed}.")
    return objects


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class SchemaNode(BaseModel):
    """Base schema model with strict validation and serialization helpers.

    Notes
    -----
    - ``validate_assignment=True`` ensures direct field reassignment is checked.
    - ``arbitrary_types_allowed=True`` allows reuse of canonical Refua object
      types such as ``Protein`` and ``SmallMolecule`` without wrapping them.
    - ``extra="forbid"`` prevents silent acceptance of misspelled or undefined
      fields when ingesting portfolio payloads.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the schema node into a plain Python mapping."""
        from .io import schema_to_mapping

        payload = schema_to_mapping(self)
        if not isinstance(payload, dict):
            raise TypeError(f"{type(self).__name__} did not serialize to a mapping.")
        return payload


class Evidence(SchemaNode):
    """Evidence supporting a disease hypothesis, rationale, or drug decision."""

    evidence_id: IdentifierStr = Field(
        ...,
        description="Stable evidence identifier used across portfolio artifacts.",
    )
    title: NonEmptyStr = Field(
        ...,
        description="Human-readable title summarizing the evidence item.",
    )
    summary: NonEmptyStr = Field(
        ...,
        description="Concise narrative describing why the evidence matters.",
    )
    source_type: NonEmptyStr = Field(
        default="literature",
        description="Source category such as literature, dataset, expert_opinion, or experiment.",
    )
    source: str | None = Field(
        default=None,
        description="Free-text citation, dataset name, lab notebook, or system of record.",
    )
    url: str | None = Field(
        default=None,
        description="Optional URL pointing to the primary evidence record.",
    )
    confidence_score: float | None = Field(
        default=None,
        description="Confidence in the evidence quality on a 0.0 to 1.0 scale.",
    )
    metadata: MetadataDict = Field(
        default_factory=dict,
        description="Additional structured evidence annotations not captured by first-class fields.",
    )

    @field_validator("source", "url", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        return _strip_or_none(None if value is None else str(value))

    @field_validator("confidence_score")
    @classmethod
    def _validate_confidence_score(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return _validate_probability(value, field_name="confidence_score")

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: MetadataDict) -> MetadataDict:
        return _validate_mapping_keys(value, field_name="metadata")


class Biomarker(SchemaNode):
    """Biomarker associated with disease state, mechanism, response, or safety."""

    biomarker_id: IdentifierStr = Field(
        ...,
        description="Stable biomarker identifier used across diseases, rationales, and drugs.",
    )
    name: NonEmptyStr = Field(
        ...,
        description="Canonical biomarker name such as EGFR, HER2, ctDNA, or ALT.",
    )
    role: NonEmptyStr = Field(
        ...,
        description="Biomarker role such as diagnostic, predictive, prognostic, pharmacodynamic, or safety.",
    )
    value: float | str | None = Field(
        default=None,
        description="Optional representative value or categorical state for the biomarker.",
    )
    unit: str | None = Field(
        default=None,
        description="Measurement unit associated with the biomarker value when applicable.",
    )
    direction: str | None = Field(
        default=None,
        description="Expected directionality such as up, down, enriched, depleted, responder, or resistant.",
    )
    metadata: MetadataDict = Field(
        default_factory=dict,
        description="Additional structured biomarker annotations not promoted to dedicated fields.",
    )

    @field_validator("unit", "direction", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        return _strip_or_none(None if value is None else str(value))

    @field_validator("value")
    @classmethod
    def _validate_value(cls, value: float | str | None) -> float | str | None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("value must be finite when provided as a float.")
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("value cannot be blank when provided as a string.")
            return text
        return value

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: MetadataDict) -> MetadataDict:
        return _validate_mapping_keys(value, field_name="metadata")


class Assay(SchemaNode):
    """Assay definition or assay result tied to a rationale or drug candidate."""

    assay_id: IdentifierStr = Field(
        ...,
        description="Stable assay identifier for connecting protocol, results, and provenance records.",
    )
    name: NonEmptyStr = Field(
        ...,
        description="Human-readable assay name used in portfolio reviews and reports.",
    )
    assay_type: NonEmptyStr = Field(
        ...,
        description="Assay category such as biochemical, biophysical, cellular, in_vivo, ADME, or tox.",
    )
    endpoint: NonEmptyStr = Field(
        ...,
        description="Primary endpoint readout such as IC50, EC50, viability, occupancy, or exposure.",
    )
    result_value: float | str | None = Field(
        default=None,
        description="Observed endpoint value or qualitative assay call.",
    )
    unit: str | None = Field(
        default=None,
        description="Result unit such as nM, uM, mg/kg, or percent inhibition.",
    )
    system: str | None = Field(
        default=None,
        description="Experimental system or model context such as cell line, species, or matrix.",
    )
    stage: str | None = Field(
        default=None,
        description="Program stage associated with the assay, for example hit_finding or lead_optimization.",
    )
    metadata: MetadataDict = Field(
        default_factory=dict,
        description="Additional assay protocol details, controls, or batch metadata.",
    )

    @field_validator("unit", "system", "stage", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        return _strip_or_none(None if value is None else str(value))

    @field_validator("result_value")
    @classmethod
    def _validate_result_value(cls, value: float | str | None) -> float | str | None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("result_value must be finite when provided as a float.")
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("result_value cannot be blank when provided as a string.")
            return text
        return value

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: MetadataDict) -> MetadataDict:
        return _validate_mapping_keys(value, field_name="metadata")


class Modality(SchemaNode):
    """Drug modality metadata describing the therapeutic intervention class."""

    name: NonEmptyStr = Field(
        ...,
        description="Readable modality label such as oral small molecule or bispecific antibody.",
    )
    kind: NonEmptyStr = Field(
        ...,
        description="Normalized modality family such as small_molecule, antibody, protein, RNA, or cell_therapy.",
    )
    route: str | None = Field(
        default=None,
        description="Intended route of administration such as oral, iv, sc, inhaled, or topical.",
    )
    subtype: str | None = Field(
        default=None,
        description="More specific modality subtype such as ADC, PROTAC, siRNA, or peptide.",
    )
    delivery: str | None = Field(
        default=None,
        description="Delivery or formulation strategy associated with the modality.",
    )
    metadata: MetadataDict = Field(
        default_factory=dict,
        description="Extra modality metadata such as linker chemistry, vector system, or formulation class.",
    )

    @field_validator("route", "subtype", "delivery", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        return _strip_or_none(None if value is None else str(value))

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: MetadataDict) -> MetadataDict:
        return _validate_mapping_keys(value, field_name="metadata")


class AdmetProfile(SchemaNode):
    """Structured ADMET profile linked to a drug candidate."""

    profile_id: IdentifierStr = Field(
        ...,
        description="Stable identifier for the ADMET profile snapshot.",
    )
    source: NonEmptyStr = Field(
        ...,
        description="Origin of the ADMET call set, such as txgemma, in_house_model, or wet_lab_panel.",
    )
    smiles: str | None = Field(
        default=None,
        description="Canonical SMILES string for the analyzed small molecule when applicable.",
    )
    summary_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Top-level normalized summary scores, typically on a 0.0 to 1.0 scale.",
    )
    endpoint_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Per-endpoint normalized scores, typically on a 0.0 to 1.0 scale.",
    )
    endpoint_calls: dict[str, str] = Field(
        default_factory=dict,
        description="Optional categorical endpoint calls such as pass, warn, fail, substrate, or inhibitor.",
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="High-severity ADMET concerns requiring active mitigation or deselection review.",
    )
    yellow_flags: list[str] = Field(
        default_factory=list,
        description="Moderate ADMET concerns that should be tracked during optimization.",
    )
    metadata: MetadataDict = Field(
        default_factory=dict,
        description="Auxiliary model outputs, confidence values, or panel-specific annotations.",
    )

    @field_validator("smiles", mode="before")
    @classmethod
    def _normalize_smiles(cls, value: Any) -> str | None:
        return _strip_or_none(None if value is None else str(value))

    @field_validator("summary_scores")
    @classmethod
    def _validate_summary_scores(cls, value: dict[str, float]) -> dict[str, float]:
        return _validate_probability_mapping(value, field_name="summary_scores")

    @field_validator("endpoint_scores")
    @classmethod
    def _validate_endpoint_scores(cls, value: dict[str, float]) -> dict[str, float]:
        return _validate_probability_mapping(value, field_name="endpoint_scores")

    @field_validator("endpoint_calls")
    @classmethod
    def _validate_endpoint_calls(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_string_mapping(value, field_name="endpoint_calls")

    @field_validator("red_flags")
    @classmethod
    def _validate_red_flags(cls, value: list[str]) -> list[str]:
        return _validate_string_list(value, field_name="red_flags")

    @field_validator("yellow_flags")
    @classmethod
    def _validate_yellow_flags(cls, value: list[str]) -> list[str]:
        return _validate_string_list(value, field_name="yellow_flags")

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: MetadataDict) -> MetadataDict:
        return _validate_mapping_keys(value, field_name="metadata")


class ClinicalTrial(SchemaNode):
    """Clinical trial metadata with optional simulation assets from refua-clinical."""

    trial_id: IdentifierStr = Field(
        ...,
        description="Stable trial identifier within the portfolio or linked external systems.",
    )
    title: NonEmptyStr = Field(
        ...,
        description="Readable clinical trial title or working study name.",
    )
    phase: NonEmptyStr = Field(
        ...,
        description="Study phase such as Phase I, Phase II, Phase III, or exploratory.",
    )
    status: NonEmptyStr = Field(
        default="planned",
        description="Trial lifecycle status such as planned, enrolling, active, completed, or terminated.",
    )
    indication: str | None = Field(
        default=None,
        description="Disease indication or patient population targeted by the trial.",
    )
    sponsor: str | None = Field(
        default=None,
        description="Sponsor, partner, or owning organization for the trial.",
    )
    registry_id: str | None = Field(
        default=None,
        description="External registry identifier such as an NCT number when available.",
    )
    simulation_config: SimulationConfig | None = Field(
        default=None,
        description="Validated refua-clinical simulation configuration associated with the trial.",
    )
    simulation_result: TrialSimulationResult | None = Field(
        default=None,
        description="Optional refua-clinical simulation result associated with the trial.",
    )
    metadata: MetadataDict = Field(
        default_factory=dict,
        description="Additional trial metadata such as geography, inclusion rules, or operational notes.",
    )

    @field_validator("indication", "sponsor", "registry_id", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        return _strip_or_none(None if value is None else str(value))

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: MetadataDict) -> MetadataDict:
        return _validate_mapping_keys(value, field_name="metadata")

    @model_validator(mode="after")
    def _validate_simulation_assets(self) -> Self:
        if self.simulation_result is not None and self.simulation_config is None:
            self.simulation_config = self.simulation_result.config
        if (
            self.simulation_result is not None
            and self.simulation_config is not None
            and self.simulation_result.config.trial_id != self.simulation_config.trial_id
        ):
            raise ValueError(
                "simulation_result.config.trial_id must match simulation_config.trial_id."
            )
        return self

    def with_simulation(
        self,
        *,
        config: SimulationConfig | None = None,
        result: TrialSimulationResult | None = None,
    ) -> ClinicalTrial:
        """Return the trial after attaching validated simulation assets."""
        if config is not None:
            self.simulation_config = config
        if result is not None:
            self.simulation_result = result
        return self


class Drug(SchemaNode):
    """Drug candidate that addresses a rationale and carries downstream program data."""

    drug_id: IdentifierStr = Field(
        ...,
        description="Stable drug or program identifier used across discovery and development workflows.",
    )
    name: NonEmptyStr = Field(
        ...,
        description="Readable drug, lead, or asset name shown in reviews and exports.",
    )
    modality: Modality = Field(
        ...,
        description="Validated modality metadata describing the therapeutic intervention class.",
    )
    mechanism_of_action: str | None = Field(
        default=None,
        description="Mechanism-of-action narrative describing how the drug addresses the rationale.",
    )
    structures: list[SmallMolecule] = Field(
        default_factory=list,
        description="Canonical small-molecule structures associated with the drug candidate.",
    )
    refua_objects: list[RefuaObject] = Field(
        default_factory=list,
        description="Additional canonical Refua objects such as Protein, Binder, or Complex linked to the drug.",
    )
    admet_profiles: list[AdmetProfile] = Field(
        default_factory=list,
        description="ADMET profiles supporting candidate triage and optimization decisions.",
    )
    assays: list[Assay] = Field(
        default_factory=list,
        description="Assay results or assay definitions attached directly to the drug program.",
    )
    biomarkers: list[Biomarker] = Field(
        default_factory=list,
        description="Biomarkers used to stratify response, safety, or pharmacodynamic activity for the drug.",
    )
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="Evidence supporting the drug hypothesis, performance, or developability profile.",
    )
    preclinical_studies: list[PreclinicalStudySpec] = Field(
        default_factory=list,
        description="Validated refua-preclinical study specifications associated with the drug.",
    )
    clinical_trials: list[ClinicalTrial] = Field(
        default_factory=list,
        description="Clinical trials, planned or executed, associated with the drug.",
    )
    artifact_refs: list[ArtifactRef] = Field(
        default_factory=list,
        description="Artifact references pointing to reports, models, or serialized outputs for the drug.",
    )
    evidence_bundles: list[EvidenceBundleManifest] = Field(
        default_factory=list,
        description="Regulatory evidence bundle manifests summarizing traceable documentation for the drug.",
    )
    decision_records: list[DecisionRecord] = Field(
        default_factory=list,
        description="Decision lineage records explaining critical choices for the drug program.",
    )
    data_provenance: list[DataProvenance] = Field(
        default_factory=list,
        description="Source dataset provenance associated with drug evaluations or reports.",
    )
    model_provenance: list[ModelProvenance] = Field(
        default_factory=list,
        description="Model provenance records associated with in silico outputs for the drug.",
    )
    metadata: MetadataDict = Field(
        default_factory=dict,
        description="Additional program metadata not represented in first-class drug fields.",
    )

    @field_validator("mechanism_of_action", mode="before")
    @classmethod
    def _normalize_mechanism(cls, value: Any) -> str | None:
        return _strip_or_none(None if value is None else str(value))

    @field_validator("structures")
    @classmethod
    def _validate_structures(cls, value: list[SmallMolecule]) -> list[SmallMolecule]:
        for item in value:
            if not isinstance(item, SmallMolecule):
                raise TypeError("structures entries must be SmallMolecule instances.")
        return value

    @field_validator("refua_objects")
    @classmethod
    def _validate_refua_objects_field(cls, value: list[RefuaObject]) -> list[RefuaObject]:
        return _validate_refua_objects(value, field_name="refua_objects")

    @field_validator("preclinical_studies")
    @classmethod
    def _validate_preclinical_studies(
        cls,
        value: list[PreclinicalStudySpec],
    ) -> list[PreclinicalStudySpec]:
        for item in value:
            if not isinstance(item, PreclinicalStudySpec):
                raise TypeError("preclinical_studies entries must be PreclinicalStudySpec instances.")
        return value

    @field_validator("artifact_refs")
    @classmethod
    def _validate_artifact_refs(cls, value: list[ArtifactRef]) -> list[ArtifactRef]:
        for item in value:
            if not isinstance(item, ArtifactRef):
                raise TypeError("artifact_refs entries must be ArtifactRef instances.")
        return value

    @field_validator("evidence_bundles")
    @classmethod
    def _validate_evidence_bundles(
        cls,
        value: list[EvidenceBundleManifest],
    ) -> list[EvidenceBundleManifest]:
        for item in value:
            if not isinstance(item, EvidenceBundleManifest):
                raise TypeError(
                    "evidence_bundles entries must be EvidenceBundleManifest instances."
                )
        return value

    @field_validator("decision_records")
    @classmethod
    def _validate_decision_records(cls, value: list[DecisionRecord]) -> list[DecisionRecord]:
        for item in value:
            if not isinstance(item, DecisionRecord):
                raise TypeError("decision_records entries must be DecisionRecord instances.")
        return value

    @field_validator("data_provenance")
    @classmethod
    def _validate_data_provenance(cls, value: list[DataProvenance]) -> list[DataProvenance]:
        for item in value:
            if not isinstance(item, DataProvenance):
                raise TypeError("data_provenance entries must be DataProvenance instances.")
        return value

    @field_validator("model_provenance")
    @classmethod
    def _validate_model_provenance(
        cls,
        value: list[ModelProvenance],
    ) -> list[ModelProvenance]:
        for item in value:
            if not isinstance(item, ModelProvenance):
                raise TypeError("model_provenance entries must be ModelProvenance instances.")
        return value

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: MetadataDict) -> MetadataDict:
        return _validate_mapping_keys(value, field_name="metadata")

    @classmethod
    def from_smiles(
        cls,
        *,
        drug_id: str,
        name: str,
        smiles: str,
        modality: Modality | None = None,
        mechanism_of_action: str | None = None,
    ) -> Drug:
        """Construct a drug candidate from a canonical SMILES string."""
        resolved_modality = modality or Modality(
            name="small molecule",
            kind="small_molecule",
        )
        return cls(
            drug_id=drug_id,
            name=name,
            modality=resolved_modality,
            mechanism_of_action=mechanism_of_action,
            structures=[SmallMolecule.from_smiles(smiles, name=name)],
        )

    def add_structure(self, molecule: SmallMolecule) -> Drug:
        """Append a validated structure to the drug program."""
        self.structures = [*self.structures, molecule]
        return self

    def add_refua_object(self, obj: RefuaObject) -> Drug:
        """Append a validated canonical Refua object to the drug."""
        self.refua_objects = [*self.refua_objects, obj]
        return self

    def add_admet_profile(self, profile: AdmetProfile) -> Drug:
        """Append a validated ADMET profile to the drug."""
        self.admet_profiles = [*self.admet_profiles, profile]
        return self

    def add_assay(self, assay: Assay) -> Drug:
        """Append a validated assay to the drug."""
        self.assays = [*self.assays, assay]
        return self

    def add_biomarker(self, biomarker: Biomarker) -> Drug:
        """Append a validated biomarker to the drug."""
        self.biomarkers = [*self.biomarkers, biomarker]
        return self

    def add_evidence(self, evidence: Evidence) -> Drug:
        """Append a validated evidence item to the drug."""
        self.evidence = [*self.evidence, evidence]
        return self

    def add_preclinical_study(self, study: PreclinicalStudySpec) -> Drug:
        """Append a validated preclinical study specification to the drug."""
        self.preclinical_studies = [*self.preclinical_studies, study]
        return self

    def add_clinical_trial(self, trial: ClinicalTrial) -> Drug:
        """Append a validated clinical trial to the drug."""
        self.clinical_trials = [*self.clinical_trials, trial]
        return self


class Rationale(SchemaNode):
    """Mechanistic rationale linking disease biology to targetable interventions."""

    rationale_id: IdentifierStr = Field(
        ...,
        description="Stable rationale identifier used across evidence, assays, and assets.",
    )
    title: NonEmptyStr = Field(
        ...,
        description="Short rationale title suitable for strategy reviews and prioritization tables.",
    )
    hypothesis: NonEmptyStr = Field(
        ...,
        description="Primary hypothesis describing why the mechanism should matter in the disease.",
    )
    mechanism: str | None = Field(
        default=None,
        description="Optional mechanistic detail describing target biology, pathway logic, or modality fit.",
    )
    proteins: list[Protein] = Field(
        default_factory=list,
        description="Target or pathway proteins directly associated with the rationale.",
    )
    refua_objects: list[RefuaObject] = Field(
        default_factory=list,
        description="Other canonical Refua objects that define the rationale, such as complexes or binders.",
    )
    biomarkers: list[Biomarker] = Field(
        default_factory=list,
        description="Biomarkers tied to patient selection, mechanism engagement, or downstream readouts.",
    )
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="Evidence items that support or challenge the rationale.",
    )
    assays: list[Assay] = Field(
        default_factory=list,
        description="Assays used to test the rationale mechanistically or translationally.",
    )
    drugs: list[Drug] = Field(
        default_factory=list,
        description="Drug candidates that explicitly address this rationale.",
    )
    metadata: MetadataDict = Field(
        default_factory=dict,
        description="Additional rationale annotations not elevated to dedicated fields.",
    )

    @field_validator("mechanism", mode="before")
    @classmethod
    def _normalize_mechanism(cls, value: Any) -> str | None:
        return _strip_or_none(None if value is None else str(value))

    @field_validator("proteins")
    @classmethod
    def _validate_proteins(cls, value: list[Protein]) -> list[Protein]:
        for item in value:
            if not isinstance(item, Protein):
                raise TypeError("proteins entries must be Protein instances.")
        return value

    @field_validator("refua_objects")
    @classmethod
    def _validate_refua_objects_field(cls, value: list[RefuaObject]) -> list[RefuaObject]:
        return _validate_refua_objects(value, field_name="refua_objects")

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: MetadataDict) -> MetadataDict:
        return _validate_mapping_keys(value, field_name="metadata")

    def add_protein(self, protein: Protein) -> Rationale:
        """Append a validated protein target or pathway member to the rationale."""
        self.proteins = [*self.proteins, protein]
        return self

    def add_refua_object(self, obj: RefuaObject) -> Rationale:
        """Append a validated canonical Refua object to the rationale."""
        self.refua_objects = [*self.refua_objects, obj]
        return self

    def add_biomarker(self, biomarker: Biomarker) -> Rationale:
        """Append a validated biomarker to the rationale."""
        self.biomarkers = [*self.biomarkers, biomarker]
        return self

    def add_evidence(self, evidence: Evidence) -> Rationale:
        """Append a validated evidence item to the rationale."""
        self.evidence = [*self.evidence, evidence]
        return self

    def add_assay(self, assay: Assay) -> Rationale:
        """Append a validated assay to the rationale."""
        self.assays = [*self.assays, assay]
        return self

    def add_drug(self, drug: Drug) -> Rationale:
        """Append a validated drug candidate to the rationale."""
        self.drugs = [*self.drugs, drug]
        return self


class Disease(SchemaNode):
    """Disease program containing one or more rationales, biomarkers, and evidence items."""

    disease_id: IdentifierStr = Field(
        ...,
        description="Stable disease program identifier used throughout the portfolio hierarchy.",
    )
    name: NonEmptyStr = Field(
        ...,
        description="Readable disease or indication name shown in strategy and program artifacts.",
    )
    therapeutic_area: str | None = Field(
        default=None,
        description="Broader therapeutic area such as oncology, immunology, neurology, or rare disease.",
    )
    stage: str | None = Field(
        default=None,
        description="Portfolio stage for the disease program, such as scout, incubation, or active.",
    )
    biomarkers: list[Biomarker] = Field(
        default_factory=list,
        description="Disease-level biomarkers used for segmentation, burden, or translational strategy.",
    )
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="Disease-level evidence supporting unmet need, tractability, or portfolio fit.",
    )
    rationales: list[Rationale] = Field(
        default_factory=list,
        description="Mechanistic rationales that make the disease actionable within the portfolio.",
    )
    metadata: MetadataDict = Field(
        default_factory=dict,
        description="Additional disease-level annotations not represented by first-class fields.",
    )

    @field_validator("therapeutic_area", "stage", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        return _strip_or_none(None if value is None else str(value))

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: MetadataDict) -> MetadataDict:
        return _validate_mapping_keys(value, field_name="metadata")

    def add_biomarker(self, biomarker: Biomarker) -> Disease:
        """Append a validated biomarker to the disease program."""
        self.biomarkers = [*self.biomarkers, biomarker]
        return self

    def add_evidence(self, evidence: Evidence) -> Disease:
        """Append a validated evidence item to the disease program."""
        self.evidence = [*self.evidence, evidence]
        return self

    def add_rationale(self, rationale: Rationale) -> Disease:
        """Append a validated rationale to the disease program."""
        self.rationales = [*self.rationales, rationale]
        return self

    def iter_drugs(self) -> list[Drug]:
        """Return a flat list of all drug candidates nested under the disease."""
        return [drug for rationale in self.rationales for drug in rationale.drugs]


class Portfolio(SchemaNode):
    """Top-level portfolio object spanning diseases, rationales, and drug programs."""

    portfolio_id: IdentifierStr = Field(
        ...,
        description="Stable portfolio identifier used for serialization, tracking, and integrations.",
    )
    name: NonEmptyStr = Field(
        ...,
        description="Readable portfolio name used in exports, reviews, and user interfaces.",
    )
    owner: str | None = Field(
        default=None,
        description="Optional individual, team, or organization responsible for the portfolio.",
    )
    strategy: str | None = Field(
        default=None,
        description="Optional strategy statement explaining the portfolio thesis or investment logic.",
    )
    diseases: list[Disease] = Field(
        default_factory=list,
        description="Disease programs included in the portfolio.",
    )
    metadata: MetadataDict = Field(
        default_factory=dict,
        description="Additional portfolio-level annotations not captured in first-class fields.",
    )

    @field_validator("owner", "strategy", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        return _strip_or_none(None if value is None else str(value))

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: MetadataDict) -> MetadataDict:
        return _validate_mapping_keys(value, field_name="metadata")

    def add_disease(self, disease: Disease) -> Portfolio:
        """Append a validated disease program to the portfolio."""
        self.diseases = [*self.diseases, disease]
        return self

    def iter_rationales(self) -> list[Rationale]:
        """Return a flat list of all rationales nested under the portfolio."""
        return [rationale for disease in self.diseases for rationale in disease.rationales]

    def iter_drugs(self) -> list[Drug]:
        """Return a flat list of all drug candidates nested under the portfolio."""
        return [drug for disease in self.diseases for drug in disease.iter_drugs()]

    def save(self, path: str | Path) -> Portfolio:
        """Serialize the portfolio to JSON or YAML based on the target suffix."""
        from .io import dump_portfolio

        dump_portfolio(path, self)
        return self

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Portfolio:
        """Construct a validated portfolio from a plain mapping."""
        from .io import portfolio_from_mapping

        return portfolio_from_mapping(data)

    @classmethod
    def load(cls, path: str | Path) -> Portfolio:
        """Load a validated portfolio from a JSON or YAML file."""
        from .io import load_portfolio

        return load_portfolio(path)


SchemaRoot = Portfolio | Disease | Rationale | Drug | ClinicalTrial

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
]
