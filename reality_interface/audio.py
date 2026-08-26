from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile


@dataclass(frozen=True)
class AudioSignal:
    """Analysis-ready view of a WAV while preserving source metadata."""

    source_path: Path
    source_sample_rate_hz: int
    source_channels: int
    duration_seconds: float
    analysis_sample_rate_hz: int
    waveform: np.ndarray

    @property
    def time_seconds(self) -> np.ndarray:
        return np.arange(self.waveform.size, dtype=np.float64) / self.analysis_sample_rate_hz


def _to_mono_float(samples: np.ndarray) -> tuple[np.ndarray, int]:
    samples = np.asarray(samples)
    if samples.size == 0:
        raise ValueError("WAV contains no samples")

    if samples.ndim == 1:
        channels = 1
        mono = samples.astype(np.float64)
    elif samples.ndim == 2:
        channels = int(samples.shape[1])
        mono = samples.astype(np.float64).mean(axis=1)
    else:
        raise ValueError(f"Unsupported WAV sample shape: {samples.shape}")

    mono -= mono.mean()
    peak = float(np.max(np.abs(mono)))
    if peak > 0:
        mono /= peak

    return mono, channels


def load_wav(
    path: str | Path,
    *,
    analysis_sample_rate_hz: int = 2000,
) -> AudioSignal:
    """Load a WAV into a normalized mono NumPy signal for analysis.

    The source file is never modified. If the source sample rate is higher
    than ``analysis_sample_rate_hz``, scipy.signal.resample_poly performs an
    anti-aliased downsample. The 2 kHz default comfortably preserves the
    Reality Interface's initial 10-300 Hz acquisition band while making
    envelope/autocorrelation work inexpensive.
    """

    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if analysis_sample_rate_hz <= 0:
        raise ValueError("analysis_sample_rate_hz must be positive")

    sample_rate_hz, samples = wavfile.read(source_path)
    if sample_rate_hz <= 0:
        raise ValueError("WAV sample rate must be positive")

    mono, channels = _to_mono_float(samples)
    duration_seconds = mono.size / float(sample_rate_hz)

    working = mono
    working_rate = int(sample_rate_hz)

    if sample_rate_hz > analysis_sample_rate_hz:
        divisor = int(np.gcd(sample_rate_hz, analysis_sample_rate_hz))
        up = analysis_sample_rate_hz // divisor
        down = sample_rate_hz // divisor
        working = signal.resample_poly(working, up, down)
        working_rate = analysis_sample_rate_hz

    return AudioSignal(
        source_path=source_path,
        source_sample_rate_hz=int(sample_rate_hz),
        source_channels=channels,
        duration_seconds=float(duration_seconds),
        analysis_sample_rate_hz=int(working_rate),
        waveform=np.asarray(working, dtype=np.float64),
    )
