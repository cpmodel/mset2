# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MINDSET** (Model of Innovation in Dynamic Low-Carbon Structural Economic and Employment Transformations) is a global, demand-driven, recursively dynamic macroeconometric simulation model. It covers 163 regions × 120 sectors and evaluates how climate, fiscal, and trade policies affect macroeconomic, sectoral, and labor market outcomes. Its core is a multi-regional input–output (MRIO) framework combined with macro-econometric equations.

## Running the Model

```bash
# Basic run (reads s_base.ini or settings.ini by default)
python MINDSET_dynamic_run.py

# With explicit scenario and matrix recalculation
python MINDSET_dynamic_run.py "Scenario_Name" "Yes"

# With scenario, recalculation, and residuals subtraction
python MINDSET_dynamic_run.py "Scenario_Name" "Yes" "GLORIA_results\\baseline_residuals.xlsx"
```

Arguments:
1. `scenario_name` — reads from `GLORIA_template/Scenarios/XXXX.xlsx`
2. `recalculate MRIO` (optional) — `"Yes"` or `1` recalculates Leontief/Ghoshian matrices
3. `residuals_file` (optional) — subtract a baseline residual from results each year

Windows batch launchers: `run_dynamic.cmd`, `run_dynamic_disagg.cmd`

## Setting Up a New Regional Aggregation

```bash
python "ParseCode\collapse_MRIO.py" "GLORIA_template\Country_groupings\new_grouping_file.xlsx"
python "ParseCode\collapse_FTT.py" "GLORIA_template\Country_groupings\new_grouping_file.xlsx"
```

## Dependencies

Install via: `pip install -r requirements.txt`

Core: `numpy`, `pandas`, `scipy`, `pyarrow`, `openpyxl`, `dill`

## Architecture

### Execution Flow

```
MINDSET_dynamic_run.py
  └─ ModelRun (SourceCode/model_class.py)
       ├─ __init__: reads .ini config, loads exog_vars, scenario, IO matrices
       ├─ run(): iterates over years [model_start, model_end]
       └─ solve_year(year):
            ├─ Calibration loop (if CALIBRATING=True): fits to historical data
            ├─ initiate_modules() [SourceCode/initiate_modules.py]: calls all
            │   sectoral modules in order and repeats until convergence
            └─ Dynamic variable update: carries output, employment, prices, CPI
                 forward to next year
```

### Module Execution Order in `initiate_modules.py`

Each year's within-year solver calls modules roughly in this order:
1. **scenario** — apply policy shocks (carbon tax, FD changes, supply constraints)
2. **ener_balance / ener_elas / cost_curves** — energy intensities, fuel substitution, emissions
3. **prod_cost** — production costs (labor + energy + intermediates)
4. **InputOutput** — reconstruct A-matrix, solve for output vector (Leontief)
5. **price** — cost-based markup pricing with margins
6. **household / government / trade** — demand responses via elasticities
7. **employment / investment / income / tax_rev / BTA / GDP** — factor markets and fiscal accounts
8. *(repeat until convergence on COND_LABOR, COND_TAX, COND_TRADE, COND_PRICE)*

### Key Source Files

| File | Role |
|------|------|
| `SourceCode/model_class.py` | `ModelRun` class — top-level orchestrator, `solve_year()` |
| `SourceCode/initiate_modules.py` | Calls all sectoral modules in order; manages within-year convergence loop |
| `SourceCode/variables.py` | `variables_table` class — stores/retrieves DataFrames with proper dimensions (163 regions × 120 sectors) |
| `SourceCode/exog_vars.py` | Loads elasticities, IO matrices, FD data from `GLORIA_template/` |
| `SourceCode/scenario.py` | Reads policy assumptions from scenario `.xlsx`; methods for carbon tax, FD shocks, household permanence |
| `SourceCode/InputOutput.py` | MRIO framework — sparse A-matrix reconstruction, output vector solution |
| `SourceCode/ener_balance.py` | Energy flows, emissions, fuel substitution (830 lines — the largest energy module) |
| `SourceCode/utils.py` | MRIO matrix/vector conversion helpers, `temporary_storage`, logging |

### Configuration (.ini files)

All `.ini` files use `[settings]` section. Key parameters:

| Parameter | Meaning |
|-----------|---------|
| `scenario_name` | Scenario file name in `GLORIA_template/Scenarios/` |
| `model_start` / `model_end` | Simulation year range |
| `CALIBRATING` | `True` = fit to historical data; `False` = endogenous forward run |
| `mrio_inverse_recalculate` | Recompute Leontief/Ghoshian matrices |
| `ftt_run` | Integrate FTT:Power sub-model |
| `SWITCH_WITHIN_YEAR_LOOP` | Enable within-year convergence iterations |
| `COND_LABOR/TAX/TRADE/PRICE` | Convergence thresholds (%) |
| `ITER_MAX` | Max within-year iterations (default 100) |
| `WRITE_AT_END` | Write results only after final year |
| `residuals_file` | Calibration residuals to subtract from results |

Active scenario configs: `s_base.ini`, `s_cprice_disagg.ini`, `s_cprice_disagg_rr.ini`, `s_EE.ini`

### Data Layout

- `GLORIA_template/` — all model inputs: scenario `.xlsx` files, elasticities, employment/investment/government parameters, energy parameters, raw GLORIA IO data
- `GLORIA_results/` — output: `FullResults_XXXX.xlsx` per run
- `Residuals/` — calibration residuals per year (`residuals_YYYY.pkl`) and error logs (`calibration_errors_YYYY.csv`)
- `Temp/` — cleared between runs; intermediate matrix storage
- `Log/` — runtime logs

### Scenario Files

Scenario assumptions live in `GLORIA_template/Scenarios/*.xlsx`. Each sheet covers a policy instrument (carbon tax, CBAM, final demand shock, investment, supply constraints, price changes, IO coefficient changes). Copy an existing scenario file and modify the relevant sheets to create a new scenario.

### FTT:Power Integration

The `MINDSET_FTT_Power/` subdirectory contains a standalone electricity sector model. Enabled via `ftt_run = True` in the `.ini` config. Conversion tables in `MINDSET_FTT_Power/Utilities/` map FTT technology categories to MINDSET investment/fuel categories.

## Output

Results are written to `GLORIA_results/FullResults_XXXX.xlsx`. The `merge_results_longformat_dynamic.py` script merges multi-scenario outputs into a long-format CSV for analysis.
