from nicegui import ui

from .results_engine import DIMENSION_LABELS, ResultsEngine, format_dimension_value
from .shared import shared_layout
from .state import state

# Display label -> internal value for the comparison selector
RESULT_TYPE_OPTIONS = {
    'Levels': 'levels',
    'Absolute difference from baseline': 'absolute_diff',
    'Relative difference from baseline': 'relative_diff',
}
_BASELINE_HINT = 'Select a baseline and at least one other scenario to enable comparison.'


def render_results_page():
    """Render the Results page for selecting scenarios and exploring outputs."""
    # Lazy import plotly only when the results page is rendered
    from plotly import graph_objects as go

    shared_layout()

    engine = ResultsEngine()
    available_scenarios = engine.get_scenario_names()
    if not available_scenarios:
        ui.notify('No result files found in the Results folder.', type='warning')

    # Comparison selector references; rebuilt inside update_dimensions() so the
    # selector sits in the same row as the dimension dropdowns.
    result_type_selector = None
    result_type_hint = None

    with ui.column().classes('w-full h-[calc(100vh-8rem)] flex no-wrap items-start'):

        # SECTION 1. Figure
        with ui.card().classes('w-full h-1/2 shadow-sm border p-0 border-gray-200'):
            plot_template = 'plotly_dark' if state.dark_mode else 'simple_white'
            fig = go.Figure()
            fig.update_layout(
                margin=dict(l=40, r=20, t=40, b=40),
                template=plot_template,
                showlegend=True,
                xaxis=dict(title='Year'),
                yaxis_title='Value',
            )
            plot = ui.plotly(fig).classes('w-full h-full p-0')

        # SECTION 2. Controls
        with ui.card().classes('w-full h-1/2 p-3 overflow-y-auto shadow-sm border border-gray-200'):
            with ui.row().classes('w-full h-full'):
                if state.dark_mode:
                    tab_style = 'vertical indicator-color=accent active-color=white active-bg-color=gray-700'
                else:
                    tab_style = 'vertical indicator-color=accent active-color=black active-bg-color=gray-200'
                with ui.tabs().props(tab_style).classes('border-r') as tabs:
                    scenarios_tab = ui.tab('Scenarios').classes('h-1/2').props('icon=folder_open')
                    analysis_tab = ui.tab('Analysis').classes('h-1/2').props('icon=bar_chart')

                with ui.tab_panels(tabs, value=scenarios_tab).classes('flex-grow h-full'):

                    # TAB 1: SCENARIOS
                    with ui.tab_panel(scenarios_tab).classes('w-full h-full p-2 overflow-hidden'):
                        with ui.row().classes('w-full h-full gap-6 overflow-y-auto'):
                            with ui.column().classes('flex-1 items-start overflow-y-auto'):
                                ui.label('Select scenarios to plot').classes('text-xs font-semibold')
                                state.selected_scenarios = [
                                    s for s in state.selected_scenarios if s in available_scenarios]
                                scenario_selector = ui.select(
                                    options=available_scenarios,
                                    label='Scenarios',
                                    multiple=True,
                                    with_input=True,
                                    value=state.selected_scenarios,
                                ).classes('w-full').props('dense use-chips')

                                baseline_selector = ui.select(
                                    options=[],
                                    label='Baseline (optional)',
                                    with_input=True,
                                    clearable=True,
                                    value=None,
                                ).classes('w-full').props('dense')

                    # TAB 2: ANALYSIS
                    with ui.tab_panel(analysis_tab).classes('w-full items-start p-2'):
                        with ui.column().classes('w-full items-start no-scroll gap-3'):
                            ui.label('Select variable').classes('text-xs p-0 justify-left font-semibold').props('dense')
                            with ui.row().classes('w-full gap-5 items-center'):
                                variable_selector = ui.select(
                                    options=[],
                                    label='Variable',
                                    value=None,
                                    with_input=True,
                                ).classes('flex-grow gap-1').props('dense')

                                def download_csv():
                                    if not plot.figure or not plot.figure.data:
                                        ui.notify('No data to download', type='warning')
                                        return
                                    import io
                                    import pandas as pd
                                    from datetime import datetime

                                    data_dict = {'Year': list(plot.figure.data[0].x)}
                                    for trace in plot.figure.data:
                                        data_dict[trace.name] = list(trace.y)
                                    df = pd.DataFrame(data_dict).melt(
                                        id_vars='Year', var_name='Scenario', value_name='Value')
                                    buffer = io.StringIO()
                                    df.to_csv(buffer, index=False)
                                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                                    ui.download(
                                        buffer.getvalue().encode(),
                                        f'{state.selected_variable or "data"}_{timestamp}.csv')
                                    ui.notify('Downloaded data', type='positive')

                                ui.button('Download data', on_click=download_csv,
                                          icon='download').classes('h-full text-xs')

                            # Dimension selectors and the comparison selector
                            # (rebuilt together when the variable changes).
                            dimension_container = ui.row().classes(
                                'w-[calc(100vw-14rem)] h-full gap-3 overflow-x-auto flex-nowrap')

        def warn_if_no_scenarios():
            if not state.selected_scenarios:
                ui.notify('Please select scenarios in the "Scenarios" tab first.',
                          type='warning')

        analysis_tab.on('click', warn_if_no_scenarios)

        # ------------------------------------------------------------ functions

        def update_baseline_options():
            baseline_selector.options = state.selected_scenarios
            if state.selected_baseline and state.selected_baseline not in state.selected_scenarios:
                state.selected_baseline = None
            baseline_selector.value = state.selected_baseline
            baseline_selector.update()
            update_result_type_availability()

        def refresh_variables():
            variables = engine.get_variables(state.selected_scenarios)
            options = {
                var: f'{var} - {desc}' if desc else var
                for var, (unit, desc) in variables.items()
            }
            if state.selected_variable not in options:
                state.selected_variable = None
            variable_selector.set_options(options, value=state.selected_variable)

        def update_result_type_availability():
            """Enable/disable comparison types that require a baseline."""
            selected = state.selected_scenarios or []
            has_baseline = bool(state.selected_baseline)
            can_show_diffs = (len(selected) >= 2 and has_baseline
                              and state.selected_baseline in selected)
            if not can_show_diffs and state.result_type != 'levels':
                state.result_type = 'levels'
            if result_type_selector is None:
                return
            if can_show_diffs:
                result_type_selector.enable()
            else:
                result_type_selector.value = 'Levels'
                result_type_selector.disable()
            result_type_hint.set_visibility(not can_show_diffs)

        def update_plot():
            if not state.selected_variable or not state.selected_scenarios:
                return
            fig = engine.extract(
                variable_key=state.selected_variable,
                scenarios=state.selected_scenarios,
                dim_selections=state.dim_selections,
                dim_aggregates=state.dim_aggregate,
                year_range=None,
                dark_mode=state.dark_mode,
                result_type=state.result_type,
                baseline_scenario=state.selected_baseline,
            )
            plot.update_figure(fig)

        def update_dimensions():
            """Rebuild the dimension selectors and the comparison selector for
            the selected variable, keeping them in one horizontal row."""
            nonlocal result_type_selector, result_type_hint
            dimension_container.clear()
            state.dim_selections = {}
            state.dim_aggregate = {}
            result_type_selector = None
            result_type_hint = None

            def make_dim_handler(dim_name, values, all_check):
                def handler(e):
                    selection = list(e.sender.value or [])
                    state.dim_selections[dim_name] = selection
                    state.dim_selection_cache[dim_name] = selection
                    all_check.value = set(selection) == set(values)
                    update_plot()
                return handler

            def make_all_handler(dim_name, values, selector):
                def handler(e):
                    selector.value = list(values) if e.value else [values[0]]
                    state.dim_selections[dim_name] = list(selector.value)
                    state.dim_selection_cache[dim_name] = list(selector.value)
                    update_plot()
                return handler

            def make_agg_handler(dim_name):
                def handler(e):
                    state.dim_aggregate[dim_name] = e.value
                    state.dim_aggregate_cache[dim_name] = e.value
                    update_plot()
                return handler

            if state.selected_variable and state.selected_scenarios:
                dims = engine.get_variable_dimensions(
                    state.selected_variable, state.selected_scenarios)
                for dim in dims:
                    dim_values = engine.get_dimension_options(
                        state.selected_scenarios, dim)
                    if not dim_values:
                        continue

                    with dimension_container:
                        with ui.column().classes('w-full h-full gap-1 min-w-56'):
                            ui.label(DIMENSION_LABELS.get(dim, dim)).classes('text-xs font-semibold')
                            dim_select = ui.select(
                                options={v: format_dimension_value(dim, v) for v in dim_values},
                                label=f'Select {DIMENSION_LABELS.get(dim, dim).lower()}',
                                multiple=True,
                                with_input=True,
                            ).classes('w-full overflow-auto').props('dense use-chips options-dense')

                            # Restore a previous selection for this dimension, or
                            # fall back to its first value.
                            cached = state.dim_selection_cache.get(dim)
                            if cached:
                                dim_select.value = [v for v in cached if v in dim_values]
                            else:
                                dim_select.value = [dim_values[0]]
                            state.dim_selections[dim] = list(dim_select.value or [])

                            with ui.row().classes('w-full gap-4'):
                                all_check = ui.checkbox('All').props('dense')
                                all_check.value = set(dim_select.value or []) == set(dim_values)
                                all_check.on_value_change(
                                    make_all_handler(dim, dim_values, dim_select))
                                agg_check = ui.checkbox('Sum').props('dense')
                                agg_check.value = state.dim_aggregate_cache.get(dim, False)
                                state.dim_aggregate[dim] = agg_check.value
                                agg_check.on_value_change(make_agg_handler(dim))

                            dim_select.on_value_change(
                                make_dim_handler(dim, dim_values, all_check))

            with dimension_container:
                with ui.column().classes(
                        'w-full h-full no-scroll gap-1 border-l border-gray-300 pl-4 min-w-44'):
                    ui.label('Compare with baseline').classes('text-xs font-semibold')
                    current_label = next(
                        (label for label, value in RESULT_TYPE_OPTIONS.items()
                         if value == state.result_type), 'Levels')
                    result_type_selector = ui.select(
                        options=list(RESULT_TYPE_OPTIONS.keys()),
                        value=current_label,
                        label='Select comparison type',
                        with_input=False,
                    ).classes('w-full').props('dense')
                    result_type_selector.on_value_change(on_result_type_change)
                    result_type_hint = ui.label(_BASELINE_HINT).classes(
                        'text-xs text-gray-600 italic')

            update_result_type_availability()

        def apply_scenario_selection():
            """Sync all controls and the plot with the selected scenarios."""
            state.selected_scenarios = list(scenario_selector.value or [])
            update_baseline_options()
            refresh_variables()
            update_dimensions()
            update_result_type_availability()
            update_plot()

        def on_scenario_change(e):
            apply_scenario_selection()

        def on_baseline_change(e):
            state.selected_baseline = e.value
            update_result_type_availability()
            update_plot()

        def on_variable_change(e):
            state.selected_variable = e.value
            update_dimensions()
            update_result_type_availability()
            update_plot()

        def on_result_type_change(e):
            state.result_type = RESULT_TYPE_OPTIONS.get(e.value, 'levels')
            update_result_type_availability()
            update_plot()

        # ---------------------------------------------------------------- wiring

        scenario_selector.on_value_change(on_scenario_change)
        baseline_selector.on_value_change(on_baseline_change)
        variable_selector.on_value_change(on_variable_change)

        # Restore the state from a previous visit to this page. Setting .value
        # programmatically does not fire on_value_change, so sync manually.
        apply_scenario_selection()
