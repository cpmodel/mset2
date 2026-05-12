# Detailed Changelog

This file records detailed technical notes on significant refactors and migrations.

---

## 2026-03-31 — Type 1 DYNAMIC variable migration to `self.V`

### Summary

All "Type 1" cross-year state variables were migrated from the plain Python dict `self.DYNAMIC` to the typed `variables_table` (`self.V`) via `self.V.write_var` / `self.V.read_var`. This centralises cross-year state in the validated variable store and removes the need for dict lookups.

### Variables migrated

| Old key in `self.DYNAMIC` | New variable name in `self.V` | Notes |
|---|---|---|
| `price_index` | `price_index` | |
| `investment_price_index` | `investment_price_index` | |
| `delta_price_yoy` | `delta_price_yoy` | Numerically identical to `dp_all`; written as raw numpy array |
| `normal_output` | `normal_output` | Written/read as DataFrame with `from_df=True` |
| `normal_output_growth_helper` | `normal_output_growth_helper` | Written as raw numpy array |
| `profit_rate_mean` | `profit_rate_mean` | In-place numpy modification possible (read_var returns reference) |
| `cpi` | `cpi` | |
| `labour_force` | `labour_force` | Column renamed `LF` → `labour_force` on write, back on read |
| `inc_exog` | `inc_exog` | Column renamed `dlabor_exog` → `inc_exog` on write, back on read |
| `gdp_history` | `gdp_base` | `gdp_base` was already written to `self.V`; DYNAMIC write removed and reads updated |

### Files changed

- `SourceCode/model_class.py`
- `SourceCode/initiate_modules.py`
- `SourceCode/ftt_power.py`

### Design notes

- `write_var(from_df=True)` requires the input DataFrame to have a column named **exactly** `var_name`; variables whose DataFrames used a different column name require a rename before write and a rename-back after read
- `read_var` returns a **direct reference** (no copy) to the stored numpy array, so in-place modifications (e.g. the `profit_rate_mean` first-year correction) propagate without an explicit write-back
- `delta_price_yoy` is stored as a flat numpy array; downstream code that needs a labelled DataFrame reconstructs it via `MRIO_vec_to_df_DEF(self.V.read_var('delta_price_yoy', year), 'dp')`
- `gdp_base` was already registered in `self.V` and written there alongside the old DYNAMIC write; migration simply removed the DYNAMIC write and updated all reads

---

## 2026-03-31 — 3D final demand variable migration to `self.V`

### Summary

Three 3-dimensional final demand consumption variables (`household_consumption`, `fcf_consumption`, `government_consumption`) were migrated from `self.DYNAMIC` to `self.V`. These are indexed by `[REG_imp × REG_exp × TRAD_COMM]` and hold constant-price consumption flows in thousands of USD.

### Variables migrated

| Old key in `self.DYNAMIC` | New variable name in `self.V` | Original column | Notes |
|---|---|---|---|
| `household_consumption` | `household_consumption` | `VIPA` | Stored as flat array; indexed form reconstructed on read |
| `fcf_consumption` | `fcf_consumption` | `VDFA` | Same pattern |
| `government_consumption` | `government_consumption` | `VIGA` | Index order `[REG_exp, REG_imp, TRAD_COMM]` on read to match downstream usage |

### Files changed

- `SourceCode/model_class.py`
- `SourceCode/initiate_modules.py`

### Design notes

- All three variables are stored as flat numpy arrays (163 regions × 163 regions × 120 sectors); downstream code that requires the original indexed DataFrame form uses `read_var(..., as_df=True).rename(columns={var_name: original_col}).set_index([...])`
- `EXOG_VARS.HH_BASE`, `EXOG_VARS.FCF_BASE`, and `EXOG_VARS.GOV_BASE` are set from `self.V` at the start of each year `> model_start`; for `year == model_start` they retain their original values loaded by `exog_vars.py`
- Init block (`year == model_start`) writes `year-1` values from the initial `EXOG_VARS` bases so the variable store has meaningful values from the start
- `government_consumption` is written in two code paths: the dynamic path (drops helper columns, renames VIGA) and the base-year fallback that resets `EXOG_VARS.GOV_BASE`'s index before writing

---

## 2026-03-31 — 4D sparse variable migration to `self.V` and new DataFrame store methods

### Summary

Four-dimensional variables (indexed by `[REG_imp × PROD_COMM × REG_exp × TRAD_COMM]`) cannot be stored as flat numpy arrays in the existing `variables_table` without prohibitive memory use. Two new methods were added to `variables_table` to handle sparse DataFrames, and the 4D variables were migrated from `self.DYNAMIC` (or equivalent local state) to `self.V`.

### New methods in `variables_table` (`SourceCode/variables.py`)

| Method | Behaviour |
|---|---|
| `write_var_df(var_name, year, df)` | Writes a DataFrame as parquet to `GLORIA_results/` following the `generate_var_table` naming convention; keeps the two most recent years in an in-memory cache (`df_data`); older years are evicted from memory (parquet on disk remains available) |
| `read_var_df(var_name, year)` | Serves from memory cache if available; loads from parquet on miss without re-caching |

Parquet file naming: `results_file_long_{scenario_name}_{var_name}_{year}.parquet`

### Variables migrated

| Variable | Source | Dimensions | Notes |
|---|---|---|---|
| `energy_flows` | local in `initiate_modules` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | Written once per year; read cross-year in `ftt_power.py` |
| `emission_cost_intermediates` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | Carbon tax incidence on intermediate flows |
| `emission_cost_hh` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | Carbon tax incidence on household consumption |
| `emission_cost_fcf` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | Carbon tax incidence on FCF |
| `emission_cost_gov` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | Carbon tax incidence on government consumption |
| `cbam_cost_intermediates` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | CBAM incidence on intermediate flows |
| `cbam_cost_hh` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | CBAM incidence on household consumption |
| `cbam_cost_fcf` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | CBAM incidence on FCF |
| `cbam_cost_gov` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | CBAM incidence on government consumption |
| `new_IO` | `IO_model.IND_BASE` (end-of-year snapshot) | `[REG_imp, PROD_COMM, REG_exp, TRAD_COMM]` | IO table (z_bp, output, a_bp, a_tech); written at end of year, consumed as `EXOG_VARS.IND_BASE` at start of next year |

### Files changed

- `SourceCode/variables.py`
- `SourceCode/initiate_modules.py`
- `SourceCode/model_class.py`
- `SourceCode/ftt_power.py`

### Design notes

- DataFrame (not `scipy.sparse`) was chosen for the sparse store: easier groupby/merge/filter operations, direct parquet serialisation, and no need to manage index mappings
- `scipy.sparse` is imported in `InputOutput.py` but is not used — actual matrix conversion goes DataFrame → dense numpy via `.unstack().to_numpy()`
- `new_IO` is not year-indexed in the original code but is effectively year-indexed (written at end of year Y, read as `year-1` at start of year Y+1); migrated accordingly
- `ftt_power.py` uses `read_var_df('energy_flows', year-1)` and a read-modify-write pattern for `energy_flows` in the same year (reads, calls `.update()`, writes back)

---

## 2026-03-31 — Eliminate redundant pre-loop parquet writes for emission/cbam cost variables

### Summary

`emission_cost_intermediates/hh/fcf/gov` and `cbam_cost_intermediates/hh/fcf/gov` followed a write → internal use → write again pattern inside `initiate_modules`. The initial write (pre-loop) was immediately overwritten by the first iteration of the within-year convergence loop. The pre-loop writes were replaced with local Python dicts (`emission_cost_dfs`, `cbam_cost_dfs`), eliminating 8 unnecessary parquet writes per simulation year.

### Pattern before

1. Pre-loop: calculate tax/cbam incidence → `self.V.write_var_df('emission_cost_*', year, ...)` × 4, `self.V.write_var_df('cbam_cost_*', year, ...)` × 4
2. Pre-loop reads: `self.V.read_var_df('emission_cost_*', year)` and `self.V.read_var_df('cbam_cost_*', year)` in tax_rev, price, and HH sections
3. Iteration loop: recalculate and `self.V.write_var_df(...)` again on every iteration

### Pattern after

1. Pre-loop: calculate → store in `emission_cost_dfs` / `cbam_cost_dfs` dicts (no V write)
2. Pre-loop reads: access `emission_cost_dfs['intermediates']` etc. directly
3. Iteration loop: recalculate and `self.V.write_var_df(...)` as before (first and only write to V)

The iteration loop's `emission_cost_old` capture uses `emission_cost_dfs['intermediates']` on the first iteration and reads from `self.V` on subsequent iterations (after the loop's own write).

### Edge case

If `SWITCH_WITHIN_YEAR_LOOP = False`, the loop body never executes and `self.V` would never receive the values. A post-loop block writes the local dicts to `self.V` in this case to ensure cross-year reads remain valid.

### Files changed

- `SourceCode/initiate_modules.py`

---
