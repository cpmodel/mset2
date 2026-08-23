from nicegui import ui

from .shared import shared_layout


def render_settings_page():
    """Render the Settings page (placeholder for a future iteration)."""
    shared_layout()

    with ui.row().classes('w-full justify-center'):
        with ui.card().classes('w-1/2 p-6 mt-8 shadow-sm border border-gray-200'):
            ui.label('Settings').classes('text-h6 mb-2')
            ui.label('Coming soon...').classes('text-body1')
