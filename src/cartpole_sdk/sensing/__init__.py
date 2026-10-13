"""Pure source adapters; providers require explicit clocks and calibration."""
from .vision import ClockMapping, VisionProvider, VisionHTTPClient
__all__ = ['ClockMapping', 'VisionProvider', 'VisionHTTPClient']
