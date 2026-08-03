from nicegui import ui

from .shared import shared_layout


def render_run_page():
    """Render the Model Run page (placeholder for now)."""
    shared_layout()

    with ui.row().classes('w-full justify-center'):
        with ui.card().classes('w-1/2 p-6 mt-8 shadow-sm border border-gray-200'):
            ui.label('Model Run').classes('text-h6 mb-2')
            ui.label('Coming soon...').classes('text-body1 mb-4')
            ui.label('In the meantime, run the model from the command line:').classes(
                'text-sm text-gray-600')
            ui.code('python MINDSET_dynamic_run.py s_base.ini', language='bash').classes(
                'w-full')
