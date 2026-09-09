"""
recent_files.py
OC_M Project Leader app — small persisted "recent files" list.
Build: 1

Stores up to MAX_RECENT full file paths, most-recent-first, in a small
JSON file inside the app's data/ folder. Deliberately minimal: no
timestamps, no metadata beyond the path itself - just enough for a
File -> Recent Files submenu to repopulate across app restarts.

Entries that no longer exist on disk are silently dropped on load
(e.g. a file on a network share that's since been moved/deleted),
rather than shown as a dead menu item that errors when clicked.
"""

import json
from pathlib import Path

MAX_RECENT = 8


class RecentFiles:
    def __init__(self, settings_path: Path):
        self._settings_path = settings_path
        self._paths: list[str] = self._load()

    def _load(self) -> list[str]:
        if not self._settings_path.is_file():
            return []
        try:
            with self._settings_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            paths = data.get("recent_files", [])
            return [p for p in paths if Path(p).is_file()]
        except (OSError, ValueError, AttributeError):
            # A corrupted or unreadable settings file should never break
            # app startup - just start with an empty recent list.
            return []

    def _save(self):
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            with self._settings_path.open("w", encoding="utf-8") as fh:
                json.dump({"recent_files": self._paths}, fh, indent=2)
        except OSError:
            # Recent-files tracking is a convenience, not core
            # functionality - a write failure here should never
            # interrupt the PI's actual Open/Save workflow.
            pass

    def get_all(self) -> list[str]:
        return list(self._paths)

    def add(self, filepath: str):
        filepath = str(Path(filepath).resolve())
        if filepath in self._paths:
            self._paths.remove(filepath)
        self._paths.insert(0, filepath)
        self._paths = self._paths[:MAX_RECENT]
        self._save()
