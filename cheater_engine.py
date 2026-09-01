"""Deterministic data-interview primitives for the MediLacra Cheater page."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import random
from typing import Any, Dict, List, Mapping

import duckdb
import pandas as pd


@dataclass(frozen=True)
class TransformationSpec:
    key: str
    label: str
    family: str
    source_a: str
    source_b: str | None = None
    group_column: str | None = None
    filter_column: str | None = None
    filter_operator: str | None = None
    filter_value: str | int | float | None = None
    aggregate_function: str | None = None
    aggregate_column: str | None = None
    join_left_key: str | None = None
    join_right_key: str | None = None
    order_column: str | None = None
    order_direction: str | None = None
    limit: int | None = None
    exercise_mode: str | None = None


SCHEMA: Dict[str, List[str]] = {
    "patients": [
        "patient_id", "patient_name", "date_of_birth", "sex", "state",
    ],
    "encounters": [
        "encounter_id", "patient_id", "visit_number", "patient_class",
        "admit_ts", "discharge_ts", "attending_provider_id",
    ],
    "orders": [
        "order_id", "patient_id", "encounter_id", "order_ts", "order_code",
    ],
    "observations": [
        "observation_id", "encounter_id", "order_id", "observation_code",
        "observation_value", "completed_time",
    ],
    "transactions": [
        "transaction_id", "encounter_id", "transaction_date",
        "transaction_amount", "billing_provider_id",
    ],
}


EXERCISES: Dict[str, TransformationSpec] = {
    "filter": TransformationSpec(
        "filter",
        "Filter rows",
        "Filter",
        "encounters",
        filter_column="patient_class",
        filter_operator="=",
        filter_value="OUTPATIENT",
    ),
    "group_aggregate": TransformationSpec(
        "group_aggregate",
        "Count encounters per patient",
        "Group + Aggregate",
        "encounters",
        group_column="patient_id",
        aggregate_function="COUNT",
        aggregate_column="encounter_id",
    ),
    "join": TransformationSpec(
        "join",
        "Join patients to encounters",
        "Join",
        "patients",
        source_b="encounters",
        join_left_key="patient_id",
        join_right_key="patient_id",
    ),
    "latest_per_group": TransformationSpec(
        "latest_per_group",
        "Latest encounter per patient",
        "Latest / Top per Group",
        "encounters",
        group_column="patient_id",
        order_column="admit_ts",
        order_direction="DESC",
        limit=1,
    ),
    "existence_quality_missing": TransformationSpec(
        "existence_quality_missing",
        "Patients with no encounters (exercise view)",
        "Missing / Duplicates",
        "patients",
        source_b="encounters_exercise",
        join_left_key="patient_id",
        join_right_key="patient_id",
        exercise_mode="drop_encounters_for_first_patient",
    ),
    "existence_quality_duplicates": TransformationSpec(
        "existence_quality_duplicates",
        "Duplicate encounter IDs (exercise view)",
        "Missing / Duplicates",
        "encounters_exercise",
        group_column="encounter_id",
        exercise_mode="duplicate_first_encounter",
    ),
}

FAMILY_OPTIONS: Mapping[str, List[str]] = {
    "Filter": ["filter"],
    "Group + Aggregate": ["group_aggregate"],
    "Join": ["join"],
    "Latest / Top per Group": ["latest_per_group"],
    "Missing / Duplicates": [
        "existence_quality_missing",
        "existence_quality_duplicates",
    ],
}


def build_cohort(
    n_patients: int = 100,
    encounters_per_patient: int = 2,
    seed: int = 42,
) -> Dict[str, pd.DataFrame]:
    """Build a clean cohort: one order, observation and transaction per encounter."""
    if n_patients < 1:
        raise ValueError("n_patients must be at least 1.")
    if encounters_per_patient < 1:
        raise ValueError("encounters_per_patient must be at least 1.")

    rng = random.Random(seed)
    base = datetime(2026, 1, 1, 8, 0, 0)
    first_names = [
        "Alex", "Jordan", "Morgan", "Casey", "Taylor", "Riley", "Avery", "Sam",
    ]
    last_names = [
        "Smith", "Jones", "Patel", "Nguyen", "Garcia", "Brown", "Wilson", "Martin",
    ]
    states = ["MA", "NH", "RI", "CT", "NY"]
    classes = ["OUTPATIENT", "INPATIENT", "EMERGENCY"]
    order_codes = ["CBC", "CMP", "A1C", "XR-CHEST"]
    obs_codes = ["HGB", "GLUCOSE", "A1C", "IMPRESSION"]

    patients = []
    encounters = []
    orders = []
    observations = []
    transactions = []

    for p_idx in range(1, n_patients + 1):
        patient_id = f"P{p_idx:04d}"
        patients.append({
            "patient_id": patient_id,
            "patient_name": (
                f"{rng.choice(last_names).upper()}, "
                f"{rng.choice(first_names).upper()}"
            ),
            "date_of_birth": (
                f"{rng.randint(1940, 2004):04d}-"
                f"{rng.randint(1, 12):02d}-"
                f"{rng.randint(1, 28):02d}"
            ),
            "sex": rng.choice(["F", "M"]),
            "state": rng.choice(states),
        })

        for e_idx in range(1, encounters_per_patient + 1):
            encounter_id = f"E{p_idx:04d}_{e_idx}"
            admit = base + timedelta(
                days=(p_idx * 3) + (e_idx * 31),
                hours=rng.randint(0, 8),
            )
            discharge = admit + timedelta(hours=rng.randint(2, 48))
            provider_id = f"PR{rng.randint(1, 15):03d}"
            order_id = f"O{p_idx:04d}_{e_idx}"

            encounters.append({
                "encounter_id": encounter_id,
                "patient_id": patient_id,
                "visit_number": f"VN{p_idx:04d}{e_idx}",
                "patient_class": classes[(p_idx + e_idx) % 3],
                "admit_ts": admit,
                "discharge_ts": discharge,
                "attending_provider_id": provider_id,
            })
            orders.append({
                "order_id": order_id,
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "order_ts": admit + timedelta(minutes=20),
                "order_code": rng.choice(order_codes),
            })
            observations.append({
                "observation_id": f"OBS{p_idx:04d}_{e_idx}",
                "encounter_id": encounter_id,
                "order_id": order_id,
                "observation_code": rng.choice(obs_codes),
                "observation_value": round(rng.uniform(1.0, 15.0), 2),
                "completed_time": admit + timedelta(hours=1),
            })
            transactions.append({
                "transaction_id": f"T{p_idx:04d}_{e_idx}",
                "encounter_id": encounter_id,
                "transaction_date": discharge,
                "transaction_amount": round(rng.uniform(40.0, 2500.0), 2),
                "billing_provider_id": provider_id,
            })

    return {
        "patients": pd.DataFrame(patients),
        "encounters": pd.DataFrame(encounters),
        "orders": pd.DataFrame(orders),
        "observations": pd.DataFrame(observations),
        "transactions": pd.DataFrame(transactions),
    }


def build_exercise_tables(
    cohort: Mapping[str, pd.DataFrame],
    spec: TransformationSpec,
) -> Dict[str, pd.DataFrame]:
    """Return isolated exercise tables without mutating the clean base cohort."""
    tables = {name: frame.copy() for name, frame in cohort.items()}

    if spec.exercise_mode == "drop_encounters_for_first_patient":
        first_patient = tables["patients"].iloc[0]["patient_id"]
        tables["encounters_exercise"] = tables["encounters"][
            tables["encounters"]["patient_id"] != first_patient
        ].copy()
    elif spec.exercise_mode == "duplicate_first_encounter":
        tables["encounters_exercise"] = pd.concat(
            [tables["encounters"], tables["encounters"].iloc[[0]]],
            ignore_index=True,
        )
    elif spec.exercise_mode is not None:
        raise ValueError(f"Unknown exercise mode: {spec.exercise_mode}")

    return tables


def semantic_steps(spec: TransformationSpec) -> List[str]:
    if spec.key == "filter":
        return [
            f"Read {spec.source_a}.",
            (
                f"Keep rows where {spec.filter_column} "
                f"{spec.filter_operator} {spec.filter_value}."
            ),
            "Preserve the source row grain.",
        ]
    if spec.key == "group_aggregate":
        return [
            f"Read {spec.source_a}.",
            f"Partition rows by {spec.group_column}.",
            (
                f"{spec.aggregate_function} {spec.aggregate_column} "
                "inside each group."
            ),
            f"Output one row per {spec.group_column}.",
        ]
    if spec.key == "join":
        return [
            f"Read {spec.source_a} and {spec.source_b}.",
            (
                f"Relate {spec.source_a}.{spec.join_left_key} to "
                f"{spec.source_b}.{spec.join_right_key}."
            ),
            (
                f"Output at the {spec.source_b} grain because the "
                "relationship is one-to-many."
            ),
        ]
    if spec.key == "latest_per_group":
        return [
            f"Read {spec.source_a}.",
            f"Partition by {spec.group_column}.",
            (
                f"Order each partition by {spec.order_column} "
                f"{spec.order_direction}."
            ),
            f"Keep the first {spec.limit} row(s) per partition.",
        ]
    if spec.key == "existence_quality_missing":
        return [
            f"Start with all {spec.source_a}.",
            (
                f"Look for matching {spec.source_b} using "
                f"{spec.join_left_key}."
            ),
            "Keep only left-side rows with no match.",
        ]
    if spec.key == "existence_quality_duplicates":
        return [
            f"Read {spec.source_a}.",
            f"Group by {spec.group_column}.",
            "Count rows in each group.",
            "Keep groups with count greater than one.",
        ]
    raise KeyError(spec.key)


def _validated_direction(spec: TransformationSpec) -> str:
    direction = (spec.order_direction or "DESC").upper()
    if direction not in {"ASC", "DESC"}:
        raise ValueError("order_direction must be ASC or DESC.")
    return direction


def _validated_limit(spec: TransformationSpec) -> int:
    limit = spec.limit or 1
    if limit < 1:
        raise ValueError("limit must be at least 1.")
    return limit


def render_sql(spec: TransformationSpec) -> str:
    if spec.key == "filter":
        return (
            f"SELECT *\n"
            f"FROM {spec.source_a}\n"
            f"WHERE {spec.filter_column} {spec.filter_operator} "
            f"'{spec.filter_value}';"
        )
    if spec.key == "group_aggregate":
        return (
            f"SELECT {spec.group_column}, "
            f"{spec.aggregate_function}({spec.aggregate_column}) "
            "AS encounter_count\n"
            f"FROM {spec.source_a}\n"
            f"GROUP BY {spec.group_column}\n"
            f"ORDER BY {spec.group_column};"
        )
    if spec.key == "join":
        return (
            "SELECT p.patient_id, p.patient_name, e.encounter_id, "
            "e.admit_ts, e.patient_class\n"
            f"FROM {spec.source_a} p\n"
            f"JOIN {spec.source_b} e\n"
            f"  ON p.{spec.join_left_key} = e.{spec.join_right_key}\n"
            "ORDER BY p.patient_id, e.admit_ts;"
        )
    if spec.key == "latest_per_group":
        direction = _validated_direction(spec)
        limit = _validated_limit(spec)
        columns = ", ".join(SCHEMA.get(spec.source_a, ["*"]))
        return (
            "WITH ranked AS (\n"
            "  SELECT *,\n"
            "         ROW_NUMBER() OVER (\n"
            f"           PARTITION BY {spec.group_column}\n"
            f"           ORDER BY {spec.order_column} {direction}\n"
            "         ) AS rn\n"
            f"  FROM {spec.source_a}\n"
            ")\n"
            f"SELECT {columns}\n"
            "FROM ranked\n"
            f"WHERE rn <= {limit}\n"
            f"ORDER BY {spec.group_column}, {spec.order_column} {direction};"
        )
    if spec.key == "existence_quality_missing":
        return (
            "SELECT p.*\n"
            f"FROM {spec.source_a} p\n"
            f"LEFT JOIN {spec.source_b} e\n"
            f"  ON p.{spec.join_left_key} = e.{spec.join_right_key}\n"
            f"WHERE e.{spec.join_right_key} IS NULL;"
        )
    if spec.key == "existence_quality_duplicates":
        return (
            f"SELECT {spec.group_column}, COUNT(*) AS row_count\n"
            f"FROM {spec.source_a}\n"
            f"GROUP BY {spec.group_column}\n"
            "HAVING COUNT(*) > 1;"
        )
    raise KeyError(spec.key)


def render_python(spec: TransformationSpec) -> str:
    if spec.key == "filter":
        return (
            "result = [\n"
            f"    row for row in {spec.source_a}\n"
            f"    if row['{spec.filter_column}'] == '{spec.filter_value}'\n"
            "]"
        )
    if spec.key == "group_aggregate":
        return (
            "counts = {}\n"
            f"for row in {spec.source_a}:\n"
            f"    key = row['{spec.group_column}']\n"
            "    counts[key] = counts.get(key, 0) + 1\n"
            "\n"
            "result = [\n"
            f"    {{'{spec.group_column}': key, "
            "'encounter_count': count}\n"
            "    for key, count in sorted(counts.items())\n"
            "]"
        )
    if spec.key == "join":
        return (
            "patient_by_id = {row['patient_id']: row for row in patients}\n"
            "result = []\n"
            "for encounter in encounters:\n"
            "    patient = patient_by_id[encounter['patient_id']]\n"
            "    result.append({\n"
            "        'patient_id': patient['patient_id'],\n"
            "        'patient_name': patient['patient_name'],\n"
            "        'encounter_id': encounter['encounter_id'],\n"
            "        'admit_ts': encounter['admit_ts'],\n"
            "        'patient_class': encounter['patient_class'],\n"
            "    })"
        )
    if spec.key == "latest_per_group":
        direction = _validated_direction(spec)
        limit = _validated_limit(spec)
        reverse = direction == "DESC"
        return (
            "groups = {}\n"
            f"for row in {spec.source_a}:\n"
            f"    key = row['{spec.group_column}']\n"
            "    groups.setdefault(key, []).append(row)\n"
            "\n"
            "result = []\n"
            "for key in sorted(groups):\n"
            "    ranked = sorted(\n"
            "        groups[key],\n"
            f"        key=lambda row: row['{spec.order_column}'],\n"
            f"        reverse={reverse},\n"
            "    )\n"
            f"    result.extend(ranked[:{limit}])"
        )
    if spec.key == "existence_quality_missing":
        return (
            "encounter_patient_ids = {\n"
            "    row['patient_id'] for row in encounters_exercise\n"
            "}\n"
            "result = [\n"
            "    patient for patient in patients\n"
            "    if patient['patient_id'] not in encounter_patient_ids\n"
            "]"
        )
    if spec.key == "existence_quality_duplicates":
        return (
            "counts = {}\n"
            "for row in encounters_exercise:\n"
            "    key = row['encounter_id']\n"
            "    counts[key] = counts.get(key, 0) + 1\n"
            "\n"
            "result = [\n"
            "    {'encounter_id': key, 'row_count': count}\n"
            "    for key, count in counts.items() if count > 1\n"
            "]"
        )
    raise KeyError(spec.key)


def _validate_read_only_sql(sql: str) -> str:
    """Accept one read-only SELECT/WITH statement for the in-memory cohort."""
    statement = sql.strip()
    if not statement:
        raise ValueError("SQL is empty.")

    statement = statement[:-1].rstrip() if statement.endswith(";") else statement
    if ";" in statement:
        raise ValueError("Run one SQL statement at a time.")

    first_word = statement.split(None, 1)[0].upper()
    if first_word not in {"SELECT", "WITH"}:
        raise ValueError(
            "Cheater SQL execution is read-only: start with SELECT or WITH."
        )

    forbidden = {
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "COPY",
        "ATTACH", "DETACH", "INSTALL", "LOAD", "EXPORT", "IMPORT", "PRAGMA",
        "CALL",
    }
    tokens = {
        token.strip("(),").upper()
        for token in statement.replace("\n", " ").split()
    }
    blocked = sorted(forbidden & tokens)
    if blocked:
        raise ValueError(f"Blocked SQL operation: {blocked[0]}.")

    return statement


def execute_sql(
    sql: str,
    cohort: Mapping[str, pd.DataFrame],
    spec: TransformationSpec,
) -> pd.DataFrame:
    """Execute edited SQL against isolated in-memory DuckDB tables."""
    statement = _validate_read_only_sql(sql)
    tables = build_exercise_tables(cohort, spec)
    con = duckdb.connect(":memory:")
    try:
        for name, frame in tables.items():
            con.register(name, frame)
        return con.execute(statement).fetchdf()
    finally:
        con.close()


_SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


def _result_to_frame(result: Any) -> pd.DataFrame:
    if isinstance(result, pd.DataFrame):
        return result.reset_index(drop=True)
    if isinstance(result, pd.Series):
        return result.to_frame().reset_index(drop=True)
    if isinstance(result, list):
        return pd.DataFrame(result)
    if isinstance(result, tuple):
        return pd.DataFrame(list(result))
    if isinstance(result, dict):
        try:
            return pd.DataFrame(result)
        except ValueError:
            return pd.DataFrame([result])
    return pd.DataFrame({"result": [result]})


def execute_python(
    code: str,
    cohort: Mapping[str, pd.DataFrame],
    spec: TransformationSpec,
) -> pd.DataFrame:
    """Execute edited plain Python against list-of-dict copies of exercise tables.

    This is a local interview sandbox, not a security boundary. Imports are disabled
    and edited code must assign its final output to ``result``.
    """
    if not code.strip():
        raise ValueError("Python code is empty.")

    tables = build_exercise_tables(cohort, spec)
    namespace: Dict[str, Any] = {
        name: frame.to_dict(orient="records")
        for name, frame in tables.items()
    }
    namespace["__builtins__"] = _SAFE_BUILTINS

    exec(code, namespace, namespace)

    if "result" not in namespace:
        raise ValueError(
            "Python code must assign the final output to a variable named 'result'."
        )

    return _result_to_frame(namespace["result"])


def cohort_counts(
    cohort: Mapping[str, pd.DataFrame],
) -> Dict[str, int]:
    return {name: len(frame) for name, frame in cohort.items()}
