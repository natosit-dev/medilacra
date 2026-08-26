import numpy as np
import pytest
from scipy.io import wavfile

from reality_interface.audio import load_wav
from reality_interface.periodicity import analyze_periodicity


def _write_repeating_bursts(
    path,
    *,
    sample_rate_hz: int = 2000,
    duration_seconds: float = 12.0,
    cycle_period_seconds: float = 0.8,
):
    t = np.arange(int(sample_rate_hz * duration_seconds)) / sample_rate_hz
    waveform = np.zeros_like(t, dtype=np.float64)

    for center in np.arange(0.5, duration_seconds - 0.2, cycle_period_seconds):
        waveform += np.exp(-0.5 * ((t - center) / 0.025) ** 2)
        waveform += 0.55 * np.exp(-0.5 * ((t - (center + 0.18)) / 0.025) ** 2)

    rng = np.random.default_rng(42)
    waveform += 0.01 * rng.normal(size=waveform.size)
    waveform /= np.max(np.abs(waveform))

    wavfile.write(path, sample_rate_hz, (waveform * 32767).astype(np.int16))


def test_periodicity_recovers_known_cycle(tmp_path):
    wav_path = tmp_path / "known_75_per_min.wav"
    _write_repeating_bursts(wav_path)

    audio = load_wav(wav_path)
    result = analyze_periodicity(audio)

    assert result.estimated_cycle_period_seconds == pytest.approx(0.8, abs=0.01)
    assert result.estimated_rate_per_minute == pytest.approx(75.0, abs=1.0)
    assert result.periodicity_score > 0.5


def test_load_wav_downsamples_without_mutating_source(tmp_path):
    wav_path = tmp_path / "high_rate.wav"
    _write_repeating_bursts(wav_path, sample_rate_hz=44100)
    original = wav_path.read_bytes()

    audio = load_wav(wav_path)

    assert audio.source_sample_rate_hz == 44100
    assert audio.analysis_sample_rate_hz == 2000
    assert wav_path.read_bytes() == original
