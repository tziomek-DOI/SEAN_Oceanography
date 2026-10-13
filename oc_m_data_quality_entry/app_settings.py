"""
app_settings.py
OC_M Project Leader app — small persisted application settings.
Version: 2026.10.08_01

## ChangeLog

2026.10.08_01: Initial version. Currently holds only the stylesheet
preference (whether to use the shared dm_tools stylesheet, or a custom
.qss path, or neither). Modeled after recent_files.py's own restraint -
a small local JSON file in the app's data/ folder, no timestamps or
metadata beyond what's actually needed.

Default (first-ever launch, no settings file yet): no stylesheet at
all, letting Qt's native style follow the OS theme (Windows dark mode
included) - per explicit developer instruction, this is the preferred
default, not the shared dm_tools stylesheet. Once the user chooses a
stylesheet option via the Settings menu, that choice persists and
becomes the default for future launches.
"""

import json
from pathlib import Path

# Mutually exclusive modes for "which stylesheet, if any, should be
# applied." Only one is ever active at a time.
STYLE_MODE_NONE = "none"          # no stylesheet - Qt native/OS theme
STYLE_MODE_SHARED = "shared"      # the dm_tools shared dm_styles.qss
STYLE_MODE_CUSTOM = "custom"      # an arbitrary .qss file the user picked


class AppSettings:
    def __init__(self, settings_path: Path):
        self._settings_path = settings_path
        data = self._load()
        self.style_mode: str = data.get("style_mode", STYLE_MODE_NONE)
        self.custom_style_path: str | None = data.get("custom_style_path")

    def _load(self) -> dict:
        if not self._settings_path.is_file():
            return {}
        try:
            with self._settings_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            # A corrupted/unreadable settings file should never block
            # startup - fall back to defaults, same philosophy as
            # recent_files.py's own _load().
            return {}

    def _save(self):
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            with self._settings_path.open("w", encoding="utf-8") as fh:
                json.dump({
                    "style_mode": self.style_mode,
                    "custom_style_path": self.custom_style_path,
                }, fh, indent=2)
        except OSError:
            # Settings persistence is a convenience, not core
            # functionality - a write failure here should never
            # interrupt the PI's actual grading workflow.
            pass

    def set_none(self):
        self.style_mode = STYLE_MODE_NONE
        self.custom_style_path = None
        self._save()

    def set_shared(self):
        self.style_mode = STYLE_MODE_SHARED
        self.custom_style_path = None
        self._save()

    def set_custom(self, path: str):
        self.style_mode = STYLE_MODE_CUSTOM
        self.custom_style_path = path
        self._save()
