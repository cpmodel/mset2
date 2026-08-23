from nicegui import ui

from .state import state


def shared_layout():
    """Render the header and footer that are shared by all pages."""

    ui.dark_mode().bind_value(state, 'dark_mode')

    ui.colors(accent='#F59E0B')

    current_path = ui.context.client.page.path
    with ui.header().classes('bg-[#1C1917] items-center justify-between p-2'):
        with ui.row().classes('items-center'):
            with ui.column().classes('gap-0 ml-4'):
                ui.label('MSET').classes('font-bold text-2xl')
                ui.label('Model frontend').classes('text-xs text-stone-400 tracking-wider')

        with ui.row().classes('gap-1 mr-4'):
            # When adding a new page, add its label, route and icon here.
            for label, path, icon in [
                ('Run', '/', 'play_circle'),
                ('Results', '/results', 'insights'),
                ('Settings', '/settings', 'settings'),
            ]:
                color = 'accent' if current_path == path else 'white'
                ui.button(
                    label, icon=icon,
                    on_click=lambda p=path: ui.navigate.to(p)
                ).props(f'flat color={color}')

    with ui.footer(fixed=False).classes('bg-[#1C1917] p-2 items-center justify-between'):
        ui.label('MSET - Model of Structural and Economic Transformations').classes('text-gray-400 text-xs ml-4')
