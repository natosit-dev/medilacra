from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

from .audio import AudioSignal, load_wav


@dataclass(frozen=True)
class PeriodicityResult:
    estimated_cycle_period_seconds: float
    estimated_rate_per_minute: float
    dominant_lag_seconds: float
    periodicity_score: float
    envelope: np.ndarray
    autocorrelation: np.ndarray
    autocorrelation_lags_seconds: np.ndarray


def analyze_periodicity(
    audio: AudioSignal,
    *,
    smooth_window_seconds: float = 0.050,
    min_rate_per_minute: float = 40.0,
    max_rate_per_minute: float = 140.0,
) -> PeriodicityResult:
    """Estimate the strongest repeating cycle in an acoustic signal.

    The waveform is converted into an amplitude envelope with a Hilbert
    transform, smoothed, then autocorrelated. Only lags corresponding to the
    configured rate window are considered. The result is a measured periodic
    rate; semantic interpretation (for example, heart rate) happens later.
    """

    if audio.waveform.size < 2:
        raise ValueError("Audio signal is too short to analyze")
    if smooth_window_seconds <= 0:
        raise ValueError("smooth_window_seconds must be positive")
    if min_rate_per_minute <= 0 or max_rate_per_minute <= 0:
        raise ValueError("Rate bounds must be positive")
    if min_rate_per_minute >= max_rate_per_minute:
        raise ValueError("min_rate_per_minute must be less than max_rate_per_minute")

    analytic = signal.hilbert(audio.waveform)
    envelope = np.abs(analytic)

    window_samples = max(
        1,
        int(round(audio.analysis_sample_rate_hz * smooth_window_seconds)),
    )
    kernel = np.ones(window_samples, dtype=np.float64) / window_samples
    envelope = np.convolve(envelope, kernel, mode="same")
    envelope = envelope - envelope.mean()

    autocorrelation = signal.correlate(
        envelope,
        envelope,
        mode="full",
        method="fft",
    )
    autocorrelation = autocorrelation[envelope.size - 1 :]
    lags_seconds = (
        np.arange(autocorrelation.size, dtype=np.float64)
        / audio.analysis_sample_rate_hz
    )

    min_period_seconds = 60.0 / max_rate_per_minute
    max_period_seconds = 60.0 / min_rate_per_minute
    plausible = (
        (lags_seconds >= min_period_seconds)
        & (lags_seconds <= max_period_seconds)
    )

    if not np.any(plausible):
        raise ValueError("Audio signal is too short for the configured rate window")

    plausible_corr = autocorrelation[plausible]
    best_offset = int(np.argmax(plausible_corr))
    best_lag = float(lags_seconds[plausible][best_offset])
    if best_lag <= 0:
        raise ValueError("No positive repeating period could be estimated")

    baseline = float(autocorrelation[0])
    periodicity_score = (
        float(plausible_corr[best_offset] / baseline)
        if baseline > 0
        else 0.0
    )

    return PeriodicityResult(
        estimated_cycle_period_seconds=best_lag,
        estimated_rate_per_minute=60.0 / best_lag,
        dominant_lag_seconds=best_lag,
        periodicity_score=periodicity_score,
        envelope=envelope,
        autocorrelation=autocorrelation,
        autocorrelation_lags_seconds=lags_seconds,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Estimate repeating cycle period and rate from a WAV file.",
    )
    parser.add_argument("wav_path")
    parser.add_argument("--min-rate", type=float, default=40.0)
    parser.add_argument("--max-rate", type=float, default=140.0)
    args = parser.parse_args()

    audio = load_wav(args.wav_path)
    result = analyze_periodicity(
        audio,
        min_rate_per_minute=args.min_rate,
        max_rate_per_minute=args.max_rate,
    )

    print(
        "estimated_cycle_period_seconds = "
        f"{result.estimated_cycle_period_seconds:.3f}"
    )
    print(
        "estimated_rate_per_minute = "
        f"{result.estimated_rate_per_minute:.1f}"
    )
    print(f"periodicity_score = {result.periodicity_score:.3f}")


if __name__ == "__main__":
    main()
