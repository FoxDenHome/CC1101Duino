"""All known protocol coders."""

from .base import Signal, SignalCoder
from .lacrosse import LacrosseSignalCoder
from .minka_aire import MinkaAireSignalCoder

ALL_CODERS: list[type[SignalCoder]] = [
    LacrosseSignalCoder,
    MinkaAireSignalCoder,
]

__all__ = ["ALL_CODERS", "Signal", "SignalCoder"]
