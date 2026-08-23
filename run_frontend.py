import os
import socket
from nicegui import ui

from GUI.page_results import render_results_page
from GUI.page_run import render_run_page
from GUI.page_settings import render_settings_page

# Ensure the frontend runs from the repo root so that the Results/ folder and
# variables.xlsx resolve correctly.
repo_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(repo_root)


def _select_port(preferred=8080, max_tries=10):
    """Return a free TCP port, trying a range first then an OS-assigned one."""
    for port in range(preferred, preferred + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex(('127.0.0.1', port)) != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@ui.page('/', title='Run | MSET')
def run_page():
    render_run_page()


@ui.page('/results', title='Results | MSET')
def results_page():
    render_results_page()


@ui.page('/settings', title='Settings | MSET')
def settings_page():
    render_settings_page()


selected_port = _select_port(8080)
if selected_port != 8080:
    print(f'Port 8080 is unavailable, starting frontend on port {selected_port} instead.')

ui.run(title='MSET', port=selected_port, reload=False)
