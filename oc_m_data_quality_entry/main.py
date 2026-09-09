"""
main.py
OC_M Project Leader data-quality entry app - entry point.
Build: 3

Normal launch (via the .bat file):
    python main.py --preload "C:\\path\\to\\oc_m_preload_2026-2026_....json" --outdir "C:\\path\\to\\output"

Direct launch from PyCharm for testing:
    Run this file with no arguments. Falls back to the hard-coded
    _DEV_DEFAULT_PRELOAD / _DEV_DEFAULT_OUTDIR paths below - update
    _DEV_DEFAULT_PRELOAD to point at a real pre-loader JSON dropped
    into this app's own data/ folder (the same folder Save/Open use
    by default), or elsewhere on your machine.

--preload is required (no sensible default exists without it).
--outdir defaults to a local .\\data\\ folder next to this script if
omitted, so a bare 'python main.py --preload X' still works.
"""

import argparse
import json
import sys
from pathlib import Path

# Shared vendored dependencies (PyQt6, etc.) live one level up from this
# app's folder, in SEAN_Data-Management/libs, shared with dm_tools and
# other sibling apps - this avoids duplicating large packages like
# PyQt6 across every app.
_APP_DIR = Path(__file__).resolve().parent
_LIBS_DIR = _APP_DIR.parent / "libs"
sys.path.insert(0, str(_LIBS_DIR))

print("APP_DIR:", _APP_DIR)
print("LIBS_DIR:", _LIBS_DIR)
print("LIBS_DIR exists:", _LIBS_DIR.exists())

from PyQt6.QtWidgets import QApplication, QMessageBox

from entry_window import OCMEntryWindow

# ---------------------------------------------------------------------------
# Shared style sheet, one level up alongside libs/, shared across apps.
# ---------------------------------------------------------------------------
_SHARED_STYLES_PATH = _APP_DIR.parent / "styles" / "dm_styles.qss"

# ---------------------------------------------------------------------------
# PyCharm / direct-run convenience defaults. Not used when --preload is
# passed on the command line (i.e. when launched via the .bat file).
# Drop a sample pre-loader JSON into this app's own data/ folder (the
# same default Save/Open location) and point this at it for testing.
# ---------------------------------------------------------------------------
_DEV_DEFAULT_PRELOAD = _APP_DIR / "data" / "oc_m_preload_sample.json"
_DEV_DEFAULT_OUTDIR = _APP_DIR / "data"


def _parse_args():
    parser = argparse.ArgumentParser(description="OC_M Project Leader data-quality entry app.")
    parser.add_argument(
        "--preload",
        default=None,
        help="Path to the pre-loader JSON file supplied by the Data Manager.",
    )
    parser.add_argument(
        "--outdir",
        default=None,
        help="Default directory offered in the Save dialog. The Project "
             "Leader may still choose a different location at Save time.",
    )
    args = parser.parse_args()

    preload_path = Path(args.preload) if args.preload else _DEV_DEFAULT_PRELOAD
    outdir_path = Path(args.outdir) if args.outdir else _DEV_DEFAULT_OUTDIR

    return preload_path, outdir_path


def _load_preload_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    preload_path, outdir_path = _parse_args()

    app = QApplication(sys.argv)

    if _SHARED_STYLES_PATH.is_file():
        with _SHARED_STYLES_PATH.open("r", encoding="utf-8") as fh:
            app.setStyleSheet(fh.read())
    else:
        print(f"Warning: shared style sheet not found at {_SHARED_STYLES_PATH}; using default Qt styling.")

    if not preload_path.is_file():
        QMessageBox.critical(
            None, "OC_M Data Quality Entry",
            f"Pre-load file not found:\n{preload_path}\n\n"
            "Contact the Data Manager for a current pre-load snapshot."
        )
        sys.exit(1)

    try:
        preload_payload = _load_preload_json(preload_path)
    except (OSError, ValueError) as exc:
        QMessageBox.critical(
            None, "OC_M Data Quality Entry",
            f"Could not read pre-load file:\n{preload_path}\n\n{exc}"
        )
        sys.exit(1)

    outdir_path.mkdir(parents=True, exist_ok=True)

    window = OCMEntryWindow(preload_payload, str(outdir_path))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
