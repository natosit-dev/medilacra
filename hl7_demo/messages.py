# messages.py
#
# HL7 v2.5 message builders for MediLacra.
#
# This module assembles the individual segments created in segments.py
# into complete HL7 messages.
#
# The canonical Patient, Encounter, Transaction, and Observation entities
# are generated and persisted before reaching this layer. These functions
# simply project that data into the appropriate HL7 message structures.

from datetime import datetime
from typing import List, Optional

from .segments import (
    seg_msh,
    seg_evn,
    seg_pid,
    seg_pv1,
    seg_orc,
    seg_obr,
    seg_obx,
    seg_obx_lines,
    seg_ft1,
    seg_dg1,
    seg_gt1,
    seg_in1,
    seg_obx_gender_identity,
    seg_obx_pronouns,
    seg_obx_spcu,
)

from .sdoh import (
    get_air_quality_by_zip,
    build_obx_air_quality,
    get_poverty_pct_by_zcta,
    build_obx_poverty_pct,
    build_obx_places_obesity,
    build_obx_unemployment,
)

from .vitals import (
    predict_vitals,
    build_obx_vitals,
)

from .models import (
    Patient,
    Encounter,
    Transaction,
    Observation,
)

from .labs import (
    build_lab_orm as _build_lab_orm,
    build_lab_oru as _build_lab_oru,
    predict_labs_for_patient,
)

from .generators import (
    choose_gender_harmony_values,
)


AIRNOW_MILES_DEFAULT = 75


# =========================================================================
# ADT^A01
# =========================================================================


def build_adt(
    p: Patient,
    enc: Encounter,
    tx: Optional[Transaction] = None,
    add_air_obx: bool = True,
    add_poverty_obx: bool = True,
    add_places_obesity_obx: bool = False,
    add_unemployment_obx: bool = False,
    miles: int = AIRNOW_MILES_DEFAULT,
    obs: Optional[Observation] = None,

    # Gender Harmony flags.
    #
    # MediLacra currently represents these concepts using OBX segments
    # because the project targets HL7 v2.5.
    add_gi_obx: bool = True,
    add_pronouns_obx: bool = True,
    add_spcu_obx: bool = True,
) -> str:
    """
    Build an HL7 v2.5 ADT^A01 admission message.

    Current structure:

        MSH
        EVN
        PID
        PV1
        OBX  SDOH / vitals / Gender Harmony
        DG1  admitting diagnosis
        GT1  guarantor, when transaction data is available
        IN1  insurance, when transaction data is available

    Transaction is optional so existing callers can still build an ADT
    without financial/insurance information.
    """

    # ---------------------------------------------------------------------
    # Required/base ADT segments
    # ---------------------------------------------------------------------

    parts = [
        seg_msh("ADT^A01"),
        seg_evn(enc, "A01"),
        seg_pid(p),
        seg_pv1(enc),
    ]

    # OBX set IDs are shared across the optional observation segments
    # appended to this ADT.
    set_id = 1


    # ---------------------------------------------------------------------
    # Air quality
    # ---------------------------------------------------------------------

    if add_air_obx and getattr(p, "zip_code", ""):
        aq = get_air_quality_by_zip(
            p.zip_code
        )

        obx_aq = build_obx_air_quality(
            aq,
            set_id=set_id,
        )

        if obx_aq:
            parts.append(obx_aq)
            set_id += 1


    # ---------------------------------------------------------------------
    # Poverty
    # ---------------------------------------------------------------------

    if add_poverty_obx and getattr(p, "zip_code", ""):
        poverty = get_poverty_pct_by_zcta(
            p.zip_code
        )

        obx_poverty = build_obx_poverty_pct(
            poverty,
            set_id=set_id,
        )

        if obx_poverty:
            parts.append(obx_poverty)
            set_id += 1


    # ---------------------------------------------------------------------
    # Synthetic vitals
    # ---------------------------------------------------------------------
    #
    # Vitals are generated from the existing lightweight MediLacra model
    # using age, poverty, and AQI as inputs.

    try:
        age = (
            datetime.now().year
            - datetime.strptime(
                p.date_of_birth,
                "%Y-%m-%d",
            ).year
        )

        poverty = (
            get_poverty_pct_by_zcta(
                p.zip_code
            )
            or 0.0
        )

        air_quality = get_air_quality_by_zip(
            p.zip_code
        )

        if air_quality:
            aqi_value = float(
                air_quality.get(
                    "aqi",
                    50,
                )
            )
        else:
            aqi_value = 50.0

        vital_values = predict_vitals(
            age,
            poverty,
            aqi_value,
        )

        vital_obxs = build_obx_vitals(
            vital_values,
            start_set_id=set_id,
        )

        parts.extend(vital_obxs)

        set_id += len(vital_obxs)

    except Exception as e:
        # Vitals are enrichment data. A failure here should not prevent
        # the core synthetic ADT from being generated.
        print(
            f"[WARN] Failed to generate vitals "
            f"for {p.patient_id}: {e}"
        )


    # ---------------------------------------------------------------------
    # Additional public SDOH measures
    # ---------------------------------------------------------------------

    if add_places_obesity_obx:
        obesity_obx = build_obx_places_obesity(
            p.zip_code,
            set_id=set_id,
        )

        if obesity_obx:
            parts.append(obesity_obx)
            set_id += 1


    if add_unemployment_obx:
        unemployment_obx = build_obx_unemployment(
            p.zip_code,
            set_id=set_id,
        )

        if unemployment_obx:
            parts.append(unemployment_obx)
            set_id += 1


    # ---------------------------------------------------------------------
    # Gender Harmony / SPCU
    # ---------------------------------------------------------------------

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Most values intentionally align with administrative sex while a
    # small percentage differ to create useful interface test cases.
    gender_values = choose_gender_harmony_values(
        getattr(
            p,
            "sex",
            "",
        ),
        match_bias=0.95,
    )


    if add_gi_obx:
        gi_code, gi_text, gi_system = (
            gender_values["gi"]
        )

        parts.append(
            seg_obx_gender_identity(
                set_id=set_id,
                gi_code=gi_code,
                gi_text=gi_text,
                gi_system=gi_system,
                effective_dt=now,
                method=(
                    "ptReport",
                    "Patient-reported",
                    "HL7",
                ),
                performing_org="MEDILACRAHS",
            )
        )

        set_id += 1


    if add_pronouns_obx:
        (
            pronoun_code,
            pronoun_text,
            pronoun_system,
        ) = gender_values["pro"]

        parts.append(
            seg_obx_pronouns(
                set_id=set_id,
                pronoun_code=pronoun_code,
                pronoun_text=pronoun_text,
                pronoun_system=pronoun_system,
                effective_dt=now,
            )
        )

        set_id += 1


    if add_spcu_obx:
        (
            spcu_code,
            spcu_text,
            spcu_system,
        ) = gender_values["spcu"]

        parts.append(
            seg_obx_spcu(
                set_id=set_id,
                spcu_code=spcu_code,
                spcu_text=spcu_text,
                spcu_system=spcu_system,
                effective_dt=now,
                method=(
                    "endo",
                    "Endocrinology assessment",
                    "HL7",
                ),
            )
        )

        set_id += 1


    # ---------------------------------------------------------------------
    # Diagnosis
    # ---------------------------------------------------------------------
    #
    # The current report provides one ICD diagnosis. For ADT it is
    # represented as the admitting diagnosis.

    if obs and obs.icd_code:
        diagnosis_datetime = (
            obs.completed_time
            or enc.admit_datetime
        )

        parts.append(
            seg_dg1(
                enc,
                icd_code=obs.icd_code,
                desc=obs.icd_description,
                set_id=1,
                diag_type="A",
                diag_dt=diagnosis_datetime,
            )
        )


    # ---------------------------------------------------------------------
    # Guarantor and insurance
    # ---------------------------------------------------------------------
    #
    # HL7 v2.5 places these toward the end of the ADT_A01 structure.
    #
    # Transaction is optional to keep build_adt backward compatible.

    if tx is not None:
        parts.append(
            seg_gt1(
                tx,
                set_id=1,
            )
        )

        parts.append(
            seg_in1(
                tx,
                set_id=1,
            )
        )


    return "\r".join(parts)


# =========================================================================
# ORU^R01 - Narrative report
# =========================================================================


def build_oru(
    p: Patient,
    enc: Encounter,
    obs_list: List[Observation],
) -> str:
    """
    Build the narrative ORU^R01 used for synthetic report results.

    Current structure:

        MSH
        PID
        PV1
        OBR
        OBX
        OBX
        ...

    Long report text is split across sequential OBX|TX segments.
    """

    parts = [
        seg_msh("ORU^R01"),
        seg_pid(p),
        seg_pv1(enc),
    ]


    # ---------------------------------------------------------------------
    # OBR
    # ---------------------------------------------------------------------

    if obs_list:
        parts.append(
            seg_obr(
                enc,
                obs_list[0],
            )
        )

    else:
        # Very small fallback OBR when no observations are supplied.
        parts.append(
            "OBR|1"
        )


    # ---------------------------------------------------------------------
    # Narrative OBX segments
    # ---------------------------------------------------------------------

    set_id = 1

    for obs in obs_list:
        obx_segments = seg_obx_lines(
            obs,
            start_set_id=set_id,
        )

        parts.extend(
            obx_segments
        )

        set_id += len(
            obx_segments
        )


    return "\r".join(parts)


# =========================================================================
# DFT^P03
# =========================================================================


def build_dft(
    p: Patient,
    enc: Encounter,
    txs: List[Transaction],
    obs_list: List[Observation],
) -> str:
    """
    Build an HL7 v2.5 DFT^P03 financial transaction message.

    Current structure:

        MSH
        EVN
        PID
        PV1
        FT1...
        DG1...
        GT1
        IN1

    DFT requires an EVN segment in HL7 v2.5.

    MediLacra currently produces one transaction per encounter, but this
    function remains list-based so multiple FT1 segments can be supported.
    """

    # ---------------------------------------------------------------------
    # Message / patient / encounter context
    # ---------------------------------------------------------------------

    parts = [
        seg_msh("DFT^P03"),
        seg_evn(enc, "P03"),
        seg_pid(p),
        seg_pv1(enc),
    ]


    # ---------------------------------------------------------------------
    # Financial transactions
    # ---------------------------------------------------------------------

    primary_observation = (
        obs_list[0]
        if obs_list
        else None
    )

    for tx in txs:
        parts.append(
            seg_ft1(
                tx,
                primary_observation,
            )
        )


    # ---------------------------------------------------------------------
    # Diagnoses
    # ---------------------------------------------------------------------
    #
    # Avoid sending duplicate DG1 segments when multiple observations
    # contain the same ICD code.

    if obs_list:
        diagnosis_set_id = 1
        seen_diagnoses = set()

        for obs in obs_list:
            icd_code = (
                obs.icd_code
                or ""
            ).strip()

            if (
                not icd_code
                or icd_code in seen_diagnoses
            ):
                continue

            parts.append(
                seg_dg1(
                    enc,
                    icd_code=icd_code,
                    desc=getattr(
                        obs,
                        "icd_description",
                        "",
                    ),
                    set_id=diagnosis_set_id,
                    diag_type="F",
                    diag_dt=obs.completed_time,
                )
            )

            seen_diagnoses.add(
                icd_code
            )

            diagnosis_set_id += 1


    # ---------------------------------------------------------------------
    # Guarantor / insurance
    # ---------------------------------------------------------------------
    #
    # Insurance information is encounter-level in the current flat model,
    # so the first transaction supplies GT1 and IN1.

    if txs:
        primary_transaction = txs[0]

        parts.append(
            seg_gt1(
                primary_transaction,
                set_id=1,
            )
        )

        parts.append(
            seg_in1(
                primary_transaction,
                set_id=1,
            )
        )


    return "\r".join(parts)


# =========================================================================
# Laboratory ORM^O01
# =========================================================================


def build_orm_labs(
    p: Patient,
    enc: Encounter,
    order_code: str = "SYN_LABS",
    order_text: str = "Synthetic Lab Panel",
) -> str:
    """
    Build the existing synthetic laboratory ORM message.

    Lab-specific segment generation remains encapsulated in labs.py.
    """

    return _build_lab_orm(
        p,
        enc,
        order_code,
        order_text,
    )


# =========================================================================
# Laboratory ORU^R01
# =========================================================================


def build_oru_labs(
    p: Patient,
    enc: Encounter,
    start_set_id: int = 20,
    order_code: str = "SYN_LABS",
    order_text: str = "Synthetic Lab Panel",
) -> str:
    """
    Build the existing synthetic laboratory ORU result message.

    Laboratory values are generated from the Patient entity and then
    rendered by the lab-specific HL7 builder in labs.py.
    """

    labs = predict_labs_for_patient(
        p
    )

    return _build_lab_oru(
        p,
        enc,
        labs,
        order_code,
        order_text,
        start_set_id=start_set_id,
    )