from __future__ import annotations

import json
import os
import random
import select
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter, sleep
from typing import Iterable, Iterator

import pandas as pd


COGNITION_INTRO_VERSION = "1.1"
COGNITION_DISPLAY_VERSION = "1.0"
REACTION_BASELINE_VERSION = "1.0"
REACTION_BASELINE_PRACTICE_TRIALS = 1
REACTION_BASELINE_MEASURED_TRIALS = 5
REACTION_DELAY_MIN_SECONDS = 1.5
REACTION_DELAY_MAX_SECONDS = 4.0

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


def _clear_screen() -> None:
    """Give each measured relational trial its own visual field."""

    command = "cls" if os.name == "nt" else "clear"
    result = os.system(command)
    if result != 0:
        # ANSI fallback for terminals where the shell clear command is unavailable.
        print("\033[2J\033[H", end="", flush=True)


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


def _run_intro_calibration() -> int:
    """Orient the participant and calibrate the four response keys.

    This stage is deliberately untimed. It reduces startup/orientation cost in
    the first measured trial and confirms that 1-4 input works as expected.
    Returns the number of incorrect calibration key presses for QA metadata.
    """

    print("\nCOGNITION TEST")
    print(
        "\n"
        "You will see a series of very simple lookup questions.\n"
        "For each one, find the requested relationship in the data shown and\n"
        "answer with 1, 2, 3, or 4.\n\n"
        "This is not an intelligence quiz, and there is no score to beat.\n"
        "The questions are intentionally simple. We are measuring how the\n"
        "representation interacts with a basic lookup task, not how smart or\n"
        "fast you are.\n\n"
        "Take one slow breath, get comfortable, and answer naturally. There is\n"
        "no need to rush. Nothing is timed until after this setup.\n\n"
        "First, calibrate the response keys by pressing 1, 2, 3, and 4 in order.\n"
    )

    invalid_attempts = 0
    for expected in ("1", "2", "3", "4"):
        while True:
            raw = input(f"Press {expected}: ").strip()
            if raw == expected:
                break
            invalid_attempts += 1
            print(f"Please press {expected}.", flush=True)

    print(
        "\nCalibration complete. Next is a simple reaction-time baseline.\n",
        flush=True,
    )
    return invalid_attempts


@contextmanager
def _single_key_mode() -> Iterator[None]:
    """Temporarily make stdin return one keypress without requiring Enter."""

    if os.name == "nt":
        yield
        return

    import termios

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    new_settings = termios.tcgetattr(fd)
    new_settings[3] &= ~(termios.ICANON | termios.ECHO)
    termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)
    try:
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _key_available() -> bool:
    if os.name == "nt":
        import msvcrt

        return bool(msvcrt.kbhit())

    readable, _, _ = select.select([sys.stdin], [], [], 0)
    return bool(readable)


def _read_single_key() -> str:
    if os.name == "nt":
        import msvcrt

        key = msvcrt.getwch()
        # Windows function/navigation keys can arrive as a two-character sequence.
        if key in {"\x00", "\xe0"} and msvcrt.kbhit():
            msvcrt.getwch()
    else:
        key = sys.stdin.read(1)

    if key == "\x03":
        raise KeyboardInterrupt
    return key


def _drain_key_buffer() -> None:
    while _key_available():
        _read_single_key()


def _run_simple_reaction_baseline() -> dict[str, object]:
    """Measure simple visual-to-key reaction time before relational cognition.

    One practice trial is followed by five measured trials. Each signal is
    preceded by a random 1.5-4.0 second delay. Premature keypresses are treated
    as false starts and the same trial is retried with a new random delay.

    Raw trial measurements and summary statistics are returned in metadata.
    They are not subtracted from the relational-cognition reaction times.
    """

    baseline_seed = random.SystemRandom().randrange(0, 2**32)
    rng = random.Random(baseline_seed)
    rows: list[dict[str, object]] = []
    total_false_starts = 0

    print(
        "SIMPLE REACTION-TIME BASELINE\n\n"
        "This is not a reasoning task.\n"
        "When READY appears, wait.\n"
        "When NOW! appears, press any key as soon as you notice it.\n"
        "You do not need to press Enter.\n\n"
        "There will be one practice trial, then five measured trials.\n"
        "The delay before NOW! changes each time, so wait for the signal.\n"
    )

    trials = [
        ("practice", 1),
        *[
            ("measured", trial_number)
            for trial_number in range(1, REACTION_BASELINE_MEASURED_TRIALS + 1)
        ],
    ]

    with _single_key_mode():
        for trial_kind, trial_number in trials:
            false_starts = 0

            while True:
                _drain_key_buffer()
                if trial_kind == "practice":
                    print("Practice trial")
                else:
                    print(
                        f"Measured trial {trial_number}/"
                        f"{REACTION_BASELINE_MEASURED_TRIALS}"
                    )
                print("READY", flush=True)

                delay_seconds = rng.uniform(
                    REACTION_DELAY_MIN_SECONDS,
                    REACTION_DELAY_MAX_SECONDS,
                )
                wait_started = perf_counter()
                false_start = False

                while perf_counter() - wait_started < delay_seconds:
                    if _key_available():
                        _read_single_key()
                        _drain_key_buffer()
                        false_starts += 1
                        total_false_starts += 1
                        false_start = True
                        print(
                            "\nToo early — wait for NOW!. Retrying this trial.\n",
                            flush=True,
                        )
                        sleep(0.25)
                        break
                    sleep(0.005)

                if false_start:
                    continue

                print("NOW!", flush=True)
                started = perf_counter()
                key = _read_single_key()
                reaction_ms = (perf_counter() - started) * 1000.0
                _drain_key_buffer()

                rows.append(
                    {
                        "trial_kind": trial_kind,
                        "trial_number": trial_number,
                        "delay_ms": round(delay_seconds * 1000.0, 3),
                        "reaction_time_ms": round(reaction_ms, 3),
                        "false_starts_before_trial": false_starts,
                        "key": repr(key),
                    }
                )

                if trial_kind == "practice":
                    print("\nPractice complete.\n", flush=True)
                else:
                    print("\nRecorded.\n", flush=True)
                break

    measured = [
        float(row["reaction_time_ms"])
        for row in rows
        if row["trial_kind"] == "measured"
    ]

    if measured:
        series = pd.Series(measured, dtype="float64")
        summary = {
            "median_ms": round(float(series.median()), 3),
            "mean_ms": round(float(series.mean()), 3),
            "min_ms": round(float(series.min()), 3),
            "max_ms": round(float(series.max()), 3),
        }
    else:
        summary = {
            "median_ms": None,
            "mean_ms": None,
            "min_ms": None,
            "max_ms": None,
        }

    print(
        "Reaction baseline complete. The relational lookup questions begin now.\n",
        flush=True,
    )

    return {
        "version": REACTION_BASELINE_VERSION,
        "status": "complete",
        "seed": baseline_seed,
        "practice_trials_requested": REACTION_BASELINE_PRACTICE_TRIALS,
        "measured_trials_requested": REACTION_BASELINE_MEASURED_TRIALS,
        "measured_trials_completed": len(measured),
        "delay_min_seconds": REACTION_DELAY_MIN_SECONDS,
        "delay_max_seconds": REACTION_DELAY_MAX_SECONDS,
        "false_starts": total_false_starts,
        **summary,
        "trials": rows,
    }


def run_cognition_session(
    cases: Iterable[object],
    questions_per_layout: int = 5,
    seed: int = 143,
    layout_order: str = "random",
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run the interactive human cognition portion of the experiment.

    Returns a results dataframe plus session metadata. The intro/key calibration
    is untimed. A simple visual reaction-time baseline is measured next, then the
    relational lookup trials begin. Each relational trial receives a clean
    terminal screen before its timer starts. Invalid responses during relational
    trials do not reset the reaction timer. Keyboard interrupt/EOF preserves
    completed relational answers.
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
            "intro_version": COGNITION_INTRO_VERSION,
            "display_version": COGNITION_DISPLAY_VERSION,
            "calibration_completed": False,
            "calibration_invalid_attempts": 0,
            "reaction_baseline": {
                "version": REACTION_BASELINE_VERSION,
                "status": "skipped",
                "reason": skip_reason,
            },
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

    rows: list[dict[str, object]] = []
    presentation_order = 0
    status = "complete"
    reason: str | None = None
    calibration_completed = False
    calibration_invalid_attempts = 0
    reaction_baseline_meta: dict[str, object] = {
        "version": REACTION_BASELINE_VERSION,
        "status": "pending",
    }

    try:
        calibration_invalid_attempts = _run_intro_calibration()
        calibration_completed = True
        reaction_baseline_meta = _run_simple_reaction_baseline()

        for layout in layouts:
            for within_layout, stimulus in enumerate(stimulus_sets[layout], start=1):
                presentation_order += 1
                _clear_screen()
                print("=" * 64)
                print(
                    f"QUESTION {presentation_order}/{total_questions} "
                    f"| {layout.upper()}"
                )
                print("=" * 64)
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
                print(
                    "Correct."
                    if correct
                    else f"Incorrect. Correct answer: {stimulus.correct_option}."
                )
                sleep(0.4)

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
        if reaction_baseline_meta.get("status") == "pending":
            reaction_baseline_meta = {
                **reaction_baseline_meta,
                "status": "interrupted",
            }
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
        "intro_version": COGNITION_INTRO_VERSION,
        "display_version": COGNITION_DISPLAY_VERSION,
        "calibration_completed": calibration_completed,
        "calibration_invalid_attempts": calibration_invalid_attempts,
        "reaction_baseline": reaction_baseline_meta,
    }
    return results, metadata
