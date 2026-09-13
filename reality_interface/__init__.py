"""Reality Interface: measured physical signals into MediLacra interoperability flows."""

from .audio import AudioSignal, load_wav
from .periodicity import PeriodicityResult, analyze_periodicity

__all__ = [
    "AudioSignal",
    "PeriodicityResult",
    "analyze_periodicity",
    "load_wav",
]
