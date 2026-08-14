from __future__ import annotations

import json
import random
from dataclasses import dataclass
from time import perf_counter
from typing import Iterable

import pandas as pd


RESULT_COLUMNS = [
    "layout",
    "layout_order",
    "presentation_order",
    "question_number_within_layout",
    "task",
    "target_observation_id",
    "target_encounter_id",
    "target_provider_id",
    "target_provider_name",
    "correct_option",
    "selected_option",
    "correct",
    "reaction_time_ms",
    "invalid_attempts",
    "timed_out",
    "options_json",
]


@dataclass(frozen=True)
class ObservationProviderRecord:
    observation_id: str
    encounter_id: str
    provider_id: str
    provider_name: str

    @property
    def provider_label(self) -> str:
        return f"{self.provider_name} [{self.provider_id}]"


@dataclass(frozen=True)
class CognitionStimulus:
    target: ObservationProviderRecord
    records: tuple[ObservationProviderRecord, ...]
    options: tuple[str, ...]
    correct_option: int


def _short(value: object, width: int = 14) -> str:
    text = str(value)
    if len(text) <= width:
        return text
    half = max(4, (width - 1) // 2)
    return f"{text[:half]}…{text[-half:]}"


def _observation_provider_records(cases: Iterable[object]) -> list[ObservationProviderRecord]:
    records: list[ObservationProviderRecord] = []
    for case in cases:
        encounters = {str(e.encounter_id): e for e in case.encounters}
        for observation in case.observations:
            encounter = encounters.get(str(observation.encounter_id))
            if encounter is None:
                continue
            records.append(
                ObservationProviderRecord(
                    observation_id=str(observation.observation_id),
                    encounter_id=str(encounter.encounter_id),
                    provider_id=str(encounter.attending_provider_id),
                    provider_name=str(encounter.attending_provider_name),
                )
            )
    return records


def _build_stimuli(
    cases: Iterable[object],
    total_questions: int,
    seed: int,
) -> tuple[list[CognitionStimulus], str | None]:
    """Build a controlled relational lookup task from generated MediLacra state.

    Each trial asks which attending provider is associated with one observation.
    Canonical presentation requires observation -> encounter -> provider traversal;
    bespoke presentation shows the same relation already materialized on one row.
    """

    rng = random.Random(seed)
    records = _observation_provider_records(cases)

    by_encounter: dict[str, list[ObservationProviderRecord]] = {}
    for record in records:
        by_encounter.setdefault(record.encounter_id, []).append(record)

    encounter_reps: list[ObservationProviderRecord] = []
    seen_provider_labels: set[str] = set()
    for encounter_records in by_encounter.values():
        rep = encounter_records[0]
        if rep.provider_label in seen_provider_labels:
            continue
        seen_provider_labels.add(rep.provider_label)
        encounter_reps.append(rep)

    if len(encounter_reps) < 4:
        return [], (
            "Cognition test requires at least four encounters with distinct attending "
            "providers so each question can have four semantically valid options."
        )

    targets = list(records)
    rng.shuffle(targets)
    if len(targets) < total_questions:
        return [], (
            f"Cognition test requires at least {total_questions} observations for "
            "non-repeated targets. Increase generated grain or use --skip-cognition."
        )

    stimuli: list[CognitionStimulus] = []
    used_target_ids: set[tuple[str, str]] = set()

    for target in targets:
        target_key = (target.encounter_id, target.observation_id)
        if target_key in used_target_ids:
            continue

        distractor_reps = [
            rep
            for rep in encounter_reps
            if rep.encounter_id != target.encounter_id
            and rep.provider_label != target.provider_label
        ]
        if len(distractor_reps) < 3:
            continue

        chosen = [target] + rng.sample(distractor_reps, 3)
        rng.shuffle(chosen)

        option_labels = [record.provider_label for record in chosen]
        shuffled_options = list(option_labels)
        rng.shuffle(shuffled_options)
        correct_option = shuffled_options.index(target.provider_label) + 1

        stimuli.append(
            CognitionStimulus(
                target=target,
                records=tuple(chosen),
                options=tuple(shuffled_options),
                correct_option=correct_option,
            )
        )
        used_target_ids.add(target_key)
        if len(stimuli) >= total_questions:
            break

    if len(stimuli) < total_questions:
        return [], (
            "Could not construct enough non-repeated cognition trials with four "
            "distinct provider options from this generated reality."
        )

    return stimuli, None


def _render_stimulus(stimulus: CognitionStimulus, layout: str) -> str:
    lines: list[str] = []
    if layout == "canonical":
        lines.append("CANONICAL REPRESENTATION")
        lines.append("")
        lines.append("OBSERVATIONS")
        for record in stimulus.records:
            lines.append(
                f"  {_short(record.observation_id):<14} -> {_short(record.encounter_id):<14}"
            )
        lines.append("")
        lines.append("ENCOUNTERS")
        for record in stimulus.records:
            lines.append(
                f"  {_short(record.encounter_id):<14} -> {record.provider_label}"
            )
    elif layout == "bespoke":
        lines.append("BESPOKE REPRESENTATION")
        lines.append("")
        lines.append("ORU_ACTIVITY")
        for record in stimulus.records:
            lines.append(
                f"  {_short(record.observation_id):<14} -> {record.provider_label}"
            )
    else:
        raise ValueError(f"Unknown cognition layout: {layout}")

    lines.append("")
    lines.append(
        "Which attending provider goes with observation "
        f"{_short(stimulus.target.observation_id)}?"
    )
    lines.append("")
    for index, option in enumerate(stimulus.options, start=1):
        lines.append(f"  {index}. {option}")
    return "\n".join(lines)


def run_cognition_session(
    cases: Iterable[object],
    questions_per_layout: int = 5,
    seed: int = 143,
    layout_order: str = "random",
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run the interactive human cognition portion of the experiment.

    Returns a results dataframe plus session metadata. Invalid responses do not
    reset the reaction timer. Keyboard interrupt/EOF preserves partial results.
    """

    if questions_per_layout < 1:
        raise ValueError("questions_per_layout must be at least 1")
    if layout_order not in {"random", "canonical-first", "bespoke-first"}:
        raise ValueError(f"Unsupported layout_order: {layout_order}")

    rng = random.Random(seed)
    total_questions = questions_per_layout * 2
    stimuli, skip_reason = _build_stimuli(cases, total_questions, seed)
    if skip_reason:
        return pd.DataFrame(columns=RESULT_COLUMNS), {
            "status": "skipped",
            "reason": skip_reason,
            "questions_completed": 0,
            "questions_requested": total_questions,
        }

    rng.shuffle(stimuli)
    canonical_stimuli = stimuli[:questions_per_layout]
    bespoke_stimuli = stimuli[questions_per_layout:]

    if layout_order == "canonical-first":
        layouts = ["canonical", "bespoke"]
    elif layout_order == "bespoke-first":
        layouts = ["bespoke", "canonical"]
    else:
        layouts = ["canonical", "bespoke"]
        rng.shuffle(layouts)

    order_string = ">".join(layouts)
    stimulus_sets = {
        "canonical": canonical_stimuli,
        "bespoke": bespoke_stimuli,
    }

    print("\nCOGNITION TEST")
    print(
        "Answer each mapping question with 1-4. The timer starts after the "
        "question is printed. Invalid keys do not reset the timer.\n"
    )

    rows: list[dict[str, object]] = []
    presentation_order = 0
    status = "complete"
    reason: str | None = None

    try:
        for layout in layouts:
            print(f"--- {layout.upper()} BLOCK ---")
            for within_layout, stimulus in enumerate(stimulus_sets[layout], start=1):
                presentation_order += 1
                print()
                print(_render_stimulus(stimulus, layout), flush=True)
                started = perf_counter()
                invalid_attempts = 0
                selected_option: int | None = None

                while selected_option is None:
                    raw = input("Your answer [1-4]: ").strip()
                    if raw in {"1", "2", "3", "4"}:
                        selected_option = int(raw)
                    else:
                        invalid_attempts += 1
                        print("Please enter 1, 2, 3, or 4.", flush=True)

                reaction_ms = (perf_counter() - started) * 1000.0
                correct = selected_option == stimulus.correct_option
                print("Correct." if correct else f"Incorrect. Correct answer: {stimulus.correct_option}.")

                rows.append(
                    {
                        "layout": layout,
                        "layout_order": order_string,
                        "presentation_order": presentation_order,
                        "question_number_within_layout": within_layout,
                        "task": "observation_to_attending_provider",
                        "target_observation_id": stimulus.target.observation_id,
                        "target_encounter_id": stimulus.target.encounter_id,
                        "target_provider_id": stimulus.target.provider_id,
                        "target_provider_name": stimulus.target.provider_name,
                        "correct_option": stimulus.correct_option,
                        "selected_option": selected_option,
                        "correct": correct,
                        "reaction_time_ms": round(reaction_ms, 3),
                        "invalid_attempts": invalid_attempts,
                        "timed_out": False,
                        "options_json": json.dumps(stimulus.options),
                    }
                )
    except (KeyboardInterrupt, EOFError):
        status = "interrupted"
        reason = "Cognition session interrupted by user or terminal EOF."
        print("\nCognition session interrupted; preserving completed answers.")

    results = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    metadata: dict[str, object] = {
        "status": status,
        "reason": reason,
        "layout_order": order_string,
        "questions_completed": len(results),
        "questions_requested": total_questions,
        "questions_per_layout": questions_per_layout,
        "seed": seed,
        "task": "observation_to_attending_provider",
    }
    return results, metadata
