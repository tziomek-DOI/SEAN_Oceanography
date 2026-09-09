"""
version.py
OC_M Project Leader app — version metadata.

Bump VERSION and BUILD_DATE by hand when a new build is handed to the
Project Leader. This is the single source of truth for what the
Help -> About dialog displays.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class VersionInfo:
    version: str
    build_date: str
    app_name: str = "Oceanographic Survey Data Quality Report (OC-M)"


CURRENT_VERSION = VersionInfo(
    version="1.0.0",
    build_date="2026-07-15",
)
