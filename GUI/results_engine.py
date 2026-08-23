# -*- coding: utf-8 -*-
"""
Results analysis and plotting engine for the MINDSET GUI.

Reads the long-format output tables written by a model run into the
``Results/`` folder and turns them into plotly figures.

Two kinds of files are supported:

* Grouped tables ``results_file_long_{scenario}_{group_id}.{csv,parquet}``,
  one file per dimension combination, covering all years in a single file.
* Per-year tables ``results_file_long_{scenario}_{variable}_{year}.parquet``,
  one file per high-dimension variable per year.

Large parquet tables are read with row filters applied at read time.
"""

import itertools
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from plotly import graph_objects as go

#: Column names that identify each observation (docs/OUTPUT_FILES.md).
DIMENSION_COLUMNS = ('REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM', 'FD')
YEAR_COLUMN = 'year'

# When scanning the results folder, the year numbers must not be mistaken for 
# group ids. MAX_GROUP_ID is the largest plausible group id; 
# any file whose numeric suffix exceeds it is treated as a per-year file.
MAX_GROUP_ID = 99

#: Output tables only store non-zero flows, but the GUI needs to
# show zero lines for selected-but-absent combinations.
# GUI will fill in zero lines for any combination of selected dimension values 
# whose count does not exceed this cap.
_ZERO_FILL_COMBO_CAP = 10000

#: Human-readable labels for the dimension columns.
DIMENSION_LABELS = {
    'REG_imp': 'Importing region',
    'REG_exp': 'Exporting region',
    'PROD_COMM': 'Producing sector',
    'TRAD_COMM': 'Traded product',
    'FD': 'Final demand',
}

#: Human-readable labels for known dimension values. Region names come from
#: sheet R of the MSET variable list; codes without a label are displayed
#: as-is. Final demand labels have no sheet and stay hardcoded.
_REGION_LABELS = {}
_FD_LABELS = {
    'FD_1': 'Household',
    'FD_3': 'Government',
    'FD_4': 'Investment',
}

#: Source of the region and sector names shown in the GUI.
_LABELS_SOURCE = (Path(__file__).resolve().parent.parent
                  / 'Data' / 'MSET_data' / 'Variable_list_MINDSET.xlsx')

#: Sector-index labels from sheet P of the variable list (int -> name).
_SECTOR_LABELS = {}


def _load_dimension_labels():
    """Load region and sector labels from the MSET variable list once.

    The file is read a single time at module import; the label maps stay
    empty when the file is missing or unreadable, and codes are then
    displayed as-is.
    """
    global _REGION_LABELS, _SECTOR_LABELS
    if not _LABELS_SOURCE.exists():
        return
    try:
        regions = pd.read_excel(_LABELS_SOURCE, sheet_name='R')
        sectors = pd.read_excel(_LABELS_SOURCE, sheet_name='P')
    except Exception:
        return
    _REGION_LABELS = {str(a): str(n)
                      for a, n in zip(regions['Region_acronyms'], regions['Region_names'])
                      if isinstance(a, str) and a and pd.notna(n)}
    _SECTOR_LABELS = {int(k): str(v)
                      for k, v in zip(sectors['Lfd_Nr'], sectors['Sector_names'])
                      if pd.notna(k) and pd.notna(v)}


_load_dimension_labels()


def format_dimension_value(dim, value):
    """Human-readable label for a single dimension value, e.g. 'Africa (AFR)'."""
    if dim in ('REG_imp', 'REG_exp'):
        label = _REGION_LABELS.get(value)
    elif dim == 'FD':
        label = _FD_LABELS.get(value)
    elif dim in ('PROD_COMM', 'TRAD_COMM'):
        try:
            label = _SECTOR_LABELS.get(int(value))
        except (TypeError, ValueError):
            label = None
    else:
        label = None
    return f'{label} ({value})' if label else str(value)


class ResultsEngine:
    """Engine for discovering, loading and plotting MINDSET results."""

    def __init__(self, results_dir='Results', variables_file='variables.xlsx'):
        self.results_dir = Path(results_dir)
        self._variables_meta, self._variables_order = self._load_variables_meta(variables_file)
        self._grouped_files, self._per_year_files = self._scan_results_dir()

        # Caches keyed to avoid re-reading headers / data on every interaction.
        self._columns_cache = {}        # path -> list of column names
        self._scenario_vars_cache = {}  # scenario -> {variable key: descriptor}
        self._dim_values_cache = {}     # (scenario, dim) -> list of values
        self._long_cache = {}           # (scenario, key, selections) -> DataFrame
        self._years_cache = {}          # (scenario, key) -> sorted list of years

    # ------------------------------------------------------------------ setup

    def _load_variables_meta(self, variables_file):
        """Load variable metadata (dims, unit, description) from variables.xlsx."""
        meta = {}
        order = []
        if not Path(variables_file).exists():
            return meta, order
        try:
            sheet = pd.read_excel(variables_file, sheet_name='vars')
        except (ValueError, OSError):
            return meta, order
        for _, row in sheet.iterrows():
            var = row['VAR_NAME']
            if not isinstance(var, str) or not var:
                continue
            dims = [d for d in (row['DIM1'], row['DIM2'], row['DIM3'], row['DIM4'])
                    if isinstance(d, str) and d]
            unit = str(row['UNIT']) if not pd.isna(row['UNIT']) else ''
            description = str(row['Description']) if not pd.isna(row['Description']) else ''
            meta[var] = {'dims': dims, 'unit': unit, 'description': description}
            order.append(var)
        return meta, order

    def _scan_results_dir(self):
        """Scan the results folder into {scenario: {group_id: path}} and
        {scenario: {variable: [paths, ordered by year]}}."""
        grouped_files = {}
        per_year_files = {}

        grouped_pattern = re.compile(r'^results_file_long_(.+)_(\d+)\.(?:csv|parquet)$')
        for path in sorted(self.results_dir.iterdir()):
            match = grouped_pattern.match(path.name)
            if not match:
                continue
            group_id = int(match.group(2))
            if group_id > MAX_GROUP_ID:
                continue
            grouped_files.setdefault(match.group(1), {})[group_id] = path

        # Match per-year files against known scenarios. Trying the longest
        # scenario name first avoids scenario names that are prefixes of
        # others (e.g. "cprice_disagg" vs "cprice_disagg_rr"), and each file
        # is claimed by the first scenario that matches.
        claimed = set()
        for scenario in sorted(grouped_files, key=len, reverse=True):
            pattern = re.compile(
                rf'^results_file_long_{re.escape(scenario)}_(.+?)_(\d{{4}})\.parquet$')
            for path in sorted(self.results_dir.iterdir()):
                if path in claimed:
                    continue
                match = pattern.match(path.name)
                if match:
                    per_year_files.setdefault(scenario, {}).setdefault(
                        match.group(1), []).append(path)
                    claimed.add(path)

        for files_by_var in per_year_files.values():
            for files in files_by_var.values():
                files.sort(key=lambda p: int(re.search(r'_(\d{4})\.parquet$', p.name).group(1)))

        return grouped_files, per_year_files

    # --------------------------------------------------------------- discovery

    def get_scenario_names(self):
        """Return the sorted list of available scenario names."""
        return sorted(set(self._grouped_files) | set(self._per_year_files))

    def _read_columns(self, path):
        """Return the column names of a results file (cached)."""
        if path not in self._columns_cache:
            if path.suffix == '.parquet':
                self._columns_cache[path] = pq.ParquetFile(path).schema.names
            else:
                columns = pd.read_csv(path, nrows=1).columns.tolist()
                self._columns_cache[path] = [c for c in columns if isinstance(c, str) and c]
        return self._columns_cache[path]

    def _scenario_variables(self, scenario):
        """
        Map of GUI variable keys to descriptors for one scenario.

        A grouped-table value column is exposed under its own name. A per-year
        file is exposed under the variable name when it holds a single value
        column, or under ``{variable}.{column}`` when it holds several (e.g.
        ``new_IO.output``). Grouped tables take precedence over per-year files.
        """
        if scenario in self._scenario_vars_cache:
            return self._scenario_vars_cache[scenario]

        descriptors = {}
        for path in self._grouped_files.get(scenario, {}).values():
            for col in self._read_columns(path):
                if col in DIMENSION_COLUMNS or col == YEAR_COLUMN:
                    continue
                descriptors[col] = {'kind': 'grouped', 'path': path, 'value_col': col}

        for var, files in self._per_year_files.get(scenario, {}).items():
            value_cols = [c for c in self._read_columns(files[0])
                          if c not in DIMENSION_COLUMNS]
            for col in value_cols:
                key = var if len(value_cols) == 1 else f'{var}.{col}'
                if key not in descriptors:
                    descriptors[key] = {'kind': 'per_year', 'files': files, 'value_col': col}

        self._scenario_vars_cache[scenario] = descriptors
        return descriptors

    def get_variables(self, scenarios):
        """Return ``{variable key: (unit, description)}`` for the union of the
        given scenarios, ordered like variables.xlsx then alphabetically."""
        available = {}
        for scenario in scenarios:
            for key, desc in self._scenario_variables(scenario).items():
                if key not in available:
                    meta = self._variables_meta.get(key.split('.')[0])
                    available[key] = ((meta['unit'], meta['description'])
                                      if meta else ('', ''))

        ordered = [k for k in self._variables_order if k in available]
        ordered += sorted(k for k in available if k not in set(ordered))
        return {k: available[k] for k in ordered}

    def get_variable_dimensions(self, variable_key, scenarios):
        """
        Return the dimension columns of a variable.

        The data file is authoritative for the dimensions because it reflects
        the actual layout of each run (e.g. per-year cost tables carry a
        TRAD_COMM column that variables.xlsx omits).
        """
        for scenario in scenarios:
            desc = self._scenario_variables(scenario).get(variable_key)
            if desc:
                path = desc['path'] if desc['kind'] == 'grouped' else desc['files'][0]
                return [c for c in self._read_columns(path) if c in DIMENSION_COLUMNS]
        return []

    def get_dimension_options(self, scenarios, dim):
        """Return the sorted distinct values of a dimension, as the union of
        the given scenarios' value sets."""
        values = set()
        for scenario in scenarios:
            if (scenario, dim) not in self._dim_values_cache:
                self._dim_values_cache[(scenario, dim)] = self._distinct_dim_values(
                    scenario, dim)
            values |= set(self._dim_values_cache[(scenario, dim)])
        return self._sorted_values(dim, values)

    def _distinct_dim_values(self, scenario, dim):
        """Distinct values of a dimension for one scenario, read from a
        representative variable that carries the dimension."""
        for key, desc in self._scenario_variables(scenario).items():
            if dim not in self.get_variable_dimensions(key, [scenario]):
                continue
            path = desc['path'] if desc['kind'] == 'grouped' else desc['files'][0]
            if path.suffix == '.parquet':
                values = pq.read_table(path, columns=[dim]).column(dim).unique().to_pylist()
            else:
                values = pd.read_csv(path, usecols=[dim])[dim].dropna().unique().tolist()
            return values
        return []

    @staticmethod
    def _sorted_values(dim, values):
        if values and all(isinstance(v, (int, np.integer)) for v in values):
            return sorted(int(v) for v in values)
        return sorted(str(v) for v in values)

    # ------------------------------------------------------------------ loading

    @staticmethod
    def _read_with_filters(path, columns, filters):
        """
        Read a parquet file, dropping filters whose column is null-typed.

        Files written for a scenario that was not run (e.g. an empty per-year
        file) have all-null columns; pyarrow then rejects row filters against
        them, so those filters are simply skipped.
        """
        schema = pq.ParquetFile(path).schema_arrow
        valid = [(col, op, vals) for col, op, vals in filters
                 if not pa.types.is_null(schema.field(col).type)]
        return pq.read_table(path, columns=columns, filters=valid or None)

    def _available_years(self, scenario, variable_key):
        """Sorted years covered by a variable in a scenario (cached)."""
        key = (scenario, variable_key)
        if key not in self._years_cache:
            desc = self._scenario_variables(scenario).get(variable_key)
            if desc is None:
                years = []
            elif desc['kind'] == 'per_year':
                years = [int(re.search(r'_(\d{4})\.parquet$', p.name).group(1))
                         for p in desc['files']]
            else:
                path = desc['path']
                if path.suffix == '.parquet':
                    years = (pq.read_table(path, columns=[YEAR_COLUMN])[YEAR_COLUMN]
                             .unique().to_pylist())
                else:
                    years = (pd.read_csv(path, usecols=[YEAR_COLUMN])[YEAR_COLUMN]
                             .dropna().unique().tolist())
            self._years_cache[key] = sorted(int(y) for y in years)
        return self._years_cache[key]

    def _load_long(self, scenario, variable_key, dim_selections):
        """
        Load one scenario's data for a variable as a long DataFrame with
        columns [dims..., year, value], restricted to the selected dimension
        values. Returns None if the variable is not available in the scenario.
        """
        desc = self._scenario_variables(scenario).get(variable_key)
        if desc is None:
            return None

        cache_key = (scenario, variable_key, tuple(
            sorted((d, tuple(sorted(v))) for d, v in dim_selections.items())))
        if cache_key in self._long_cache:
            return self._long_cache[cache_key]

        dims = self.get_variable_dimensions(variable_key, [scenario])
        filters = [(d, 'in', list(values)) for d, values in dim_selections.items() if values]

        if desc['kind'] == 'grouped':
            path = desc['path']
            if path.suffix == '.parquet':
                df = self._read_with_filters(
                    path, dims + [YEAR_COLUMN, desc['value_col']], filters).to_pandas()
            else:
                df = pd.read_csv(path, usecols=dims + [YEAR_COLUMN, desc['value_col']])
                for dim, values in dim_selections.items():
                    if values:
                        df = df[df[dim].isin(values)]
        else:
            frames = []
            for path in desc['files']:
                table = self._read_with_filters(
                    path, dims + [desc['value_col']], filters)
                frame = table.to_pandas()
                year = int(re.search(r'_(\d{4})\.parquet$', path.name).group(1))
                frame[YEAR_COLUMN] = year
                frames.append(frame)
            df = pd.concat(frames, ignore_index=True)

        df = df.rename(columns={desc['value_col']: 'value'})
        df[YEAR_COLUMN] = df[YEAR_COLUMN].astype(int)
        self._long_cache[cache_key] = df
        return df

    # ---------------------------------------------------------------- plotting

    def extract(self, variable_key, scenarios, dim_selections, dim_aggregates,
                year_range=None, dark_mode=False, result_type='levels',
                baseline_scenario=None):
        """
        Extract data for the selected variable and scenarios into a plotly
        figure, aggregating the selected dimension values over the years.

        Args:
            variable_key: Variable key from get_variables().
            scenarios: Scenario names to plot.
            dim_selections: {dim: [values]} rows to include per dimension.
            dim_aggregates: {dim: bool} whether to sum across a dimension.
            year_range: (start, end) year window or None for all years.
            dark_mode: Use the dark plotly template.
            result_type: 'levels', 'absolute_diff' or 'relative_diff'.
            baseline_scenario: Scenario subtracted for the difference types.
        """
        fig = go.Figure()
        if not variable_key or not scenarios:
            return fig

        dims = self.get_variable_dimensions(variable_key, scenarios)
        if not dims:
            return fig

        # Restrict selections to the options available in the selected
        # scenarios, defaulting each dimension to its first value.
        filtered_selections = {}
        for dim in dims:
            options = self.get_dimension_options(scenarios, dim)
            valid = [v for v in dim_selections.get(dim, []) if v in options]
            filtered_selections[dim] = valid or ([options[0]] if options else [])

        if result_type != 'levels' and baseline_scenario and baseline_scenario in scenarios:
            baseline_series = self._extract_series(
                baseline_scenario, variable_key, filtered_selections,
                dim_aggregates, year_range)
        else:
            baseline_series = None

        for scenario in scenarios:
            if result_type != 'levels' and scenario == baseline_scenario:
                continue
            series_map = self._extract_series(
                scenario, variable_key, filtered_selections, dim_aggregates, year_range)
            if not series_map:
                continue
            for combo, (years, values) in series_map.items():
                baseline = baseline_series.get(combo) if baseline_series else None
                plot_years, transformed = self._apply_result_type(
                    years, values, baseline, result_type)
                fig.add_trace(go.Scatter(
                    x=plot_years, y=transformed, mode='lines',
                    name=self._trace_label(scenario, dims, dim_aggregates, combo)))

        meta = self._variables_meta.get(variable_key.split('.')[0], {})
        description = meta.get('description', '')
        unit = meta.get('unit', '')

        template = 'plotly_dark' if dark_mode else 'simple_white'
        if result_type == 'absolute_diff':
            y_title = f'Absolute difference from baseline ({unit})' if unit \
                else 'Absolute difference from baseline'
        elif result_type == 'relative_diff':
            y_title = 'Relative difference from baseline (%)'
        else:
            y_title = unit or 'Value'
        title = variable_key if not description else f'{variable_key} - {description}'

        fig.update_layout(
            margin=dict(l=10, r=10, t=40, b=40),
            template=template,
            showlegend=True,
            xaxis=dict(title='Year'),
            yaxis_title=y_title,
            title=dict(text=title, font=dict(size=18)),
        )
        for trace in fig.data:
            suffix = '%' if result_type == 'relative_diff' else ''
            trace.hovertemplate = (
                f'<b>%{{x}}</b><br><b>%{{fullData.name}}</b><br>Value: %{{y:.4g}}{suffix}'
                '<extra></extra>')
        return fig

    def _extract_series(self, scenario, variable_key, dim_selections,
                        dim_aggregates, year_range):
        """
        Extract one time series per combination of non-aggregated dimensions.

        Returns {combo: (years, values)} where combo is a tuple of
        (dim, value) pairs for the non-aggregated dimensions, or {} if the
        variable is not available in the scenario.
        """
        df = self._load_long(scenario, variable_key, dim_selections)
        if df is None:
            return {}

        years = self._available_years(scenario, variable_key)
        if year_range:
            years = [y for y in years if year_range[0] <= y <= year_range[1]]
        all_years = np.asarray(years, dtype=int)

        if year_range:
            df = df[(df[YEAR_COLUMN] >= year_range[0]) &
                    (df[YEAR_COLUMN] <= year_range[1])]

        dims = self.get_variable_dimensions(variable_key, [scenario])
        non_aggregated = [d for d in dims if not dim_aggregates.get(d)]

        if not non_aggregated:
            if df.empty:
                return ({(): (all_years, np.zeros(len(all_years)))}
                        if len(all_years) else {})
            summed = df.groupby([YEAR_COLUMN], as_index=False)['value'].sum()
            series = {(): (summed[YEAR_COLUMN].to_numpy(),
                           summed['value'].to_numpy())}
            return self._reindex_series(series, all_years)

        grouped = df.groupby(non_aggregated + [YEAR_COLUMN],
                             as_index=False, observed=True)['value'].sum()
        series = {}
        for keys, sub in grouped.groupby(non_aggregated, observed=True):
            combo = keys if isinstance(keys, tuple) else (keys,)
            series[tuple(zip(non_aggregated, combo))] = (
                sub[YEAR_COLUMN].to_numpy(), sub['value'].to_numpy())

        series = self._reindex_series(series, all_years)

        # Selected-but-absent combinations are all-zero flows in the sparse
        # output tables; surface them as zero lines instead of dropping them.
        if len(all_years) and len(series) <= _ZERO_FILL_COMBO_CAP:
            combos = itertools.product(
                *(dim_selections.get(d, []) for d in non_aggregated))
            for combo in combos:
                key = tuple(zip(non_aggregated, combo))
                series.setdefault(key, (all_years, np.zeros(len(all_years))))
        return series

    @staticmethod
    def _reindex_series(series, all_years):
        """Fill any years missing from each series with zeros."""
        if len(all_years) == 0:
            return series
        out = {}
        for combo, (years, values) in series.items():
            years = np.asarray(years)
            if len(years) == len(all_years) and np.array_equal(years, all_years):
                out[combo] = (years, values)
                continue
            mapping = dict(zip(years.tolist(), values.tolist()))
            out[combo] = (all_years, np.array(
                [mapping.get(int(y), 0.0) for y in all_years], dtype=float))
        return out

    @staticmethod
    def _apply_result_type(years, values, baseline, result_type):
        """
        Apply the requested transformation to a single time series.

        Returns ``(plot_years, plot_values)``. Difference types are aligned on
        the years common to both series, so a short baseline run can still be
        compared with a longer scenario run.
        """
        if result_type == 'levels' or baseline is None:
            return years, values

        baseline_years, baseline_values = baseline
        if not (len(years) == len(baseline_years) and np.array_equal(years, baseline_years)):
            common = np.intersect1d(years, baseline_years)
            if len(common) == 0:
                return years, values
            values = values[np.isin(years, common)]
            baseline_values = baseline_values[np.isin(baseline_years, common)]
            years = common

        if result_type == 'absolute_diff':
            return years, values - baseline_values
        with np.errstate(divide='ignore', invalid='ignore'):
            diff = (values - baseline_values) / np.abs(baseline_values) * 100
        return years, np.where(np.isfinite(diff), diff, 0.0)

    @staticmethod
    def _trace_label(scenario, dims, dim_aggregates, combo):
        """Trace label, e.g. 'cprice_disagg | Africa (AFR) | Sector 12'."""
        combo_map = dict(combo)
        parts = [scenario]
        for dim in dims:
            if not dim_aggregates.get(dim) and dim in combo_map:
                parts.append(format_dimension_value(dim, combo_map[dim]))
        return ' | '.join(parts)
