import csv
from pathlib import Path

SETTINGS_FILE = Path('GUI/gui_settings.csv')


def _load_gui_settings():
    """Load display settings from GUI/gui_settings.csv, returning defaults on failure."""
    defaults = {'dark_mode': True}
    if not SETTINGS_FILE.exists():
        return defaults
    try:
        with open(SETTINGS_FILE, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                key = (row.get('SETTING') or '').strip()
                value = (row.get('VALUE') or '').strip()
                if key == 'dark_mode':
                    defaults[key] = value in ('1', 'true', 'True', 'yes')
    except Exception:
        pass
    return defaults


class GUIState:
    """Class for maintaining the state of the GUI application."""

    def __init__(self):
        settings = _load_gui_settings()
        self.dark_mode = settings['dark_mode']
        # Results page state
        self.selected_scenarios = []
        self.selected_baseline = None
        self.selected_variable = None
        self.result_type = 'levels'  # Options: "levels", "absolute_diff", "relative_diff"
        # Selections keyed by dimension name, e.g. {'REG_imp': ['AFR', 'EUR']}
        self.dim_selections = {}
        self.dim_aggregate = {}
        # Caches so selections survive switching between variables
        self.dim_selection_cache = {}
        self.dim_aggregate_cache = {}


state = GUIState()
