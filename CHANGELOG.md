# Changelog


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


---

## [Unreleased]

### Added

* `scenario_figures.Rmd` to results, which produces standard charts for scenarios
* added compensation share (which is `compensation/gross disposable income`) to avoid inflating income effects, this needs to be added to the `VARIABLES_list.xlsx` and to `GLORIA_template\modelinputdata\compensation_share.csv`, format for the file is below:

| REG_imp | share_compensation_in_gross_disposable_income |
|---------|-----------------------------------------------|
| SEP     | 0.580471579                                   |
| AFR     | 0.375162795                                   |

### Fixed

* Migrated all Type 1 cross-year state variables (`price_index`, `investment_price_index`, `delta_price_yoy`, `normal_output`, `normal_output_growth_helper`, `profit_rate_mean`, `cpi`, `labour_force`, `inc_exog`, `gdp_history`) from `self.DYNAMIC` dict to `self.V` (`variables_table`); see `CHANGELOG_detailed.md` for details. _[Prepared by Claude Code]_
* Migrated 3D final demand variables (`household_consumption`, `fcf_consumption`, `government_consumption`) from `self.DYNAMIC` to `self.V`; see `CHANGELOG_detailed.md` for details. _[Prepared by Claude Code]_
* Added `write_var_df` / `read_var_df` methods to `variables_table` for sparse parquet-backed 4D DataFrame storage; migrated `energy_flows`, `emission_cost_*`, `cbam_cost_*`, and `new_IO` from `self.DYNAMIC` to `self.V`; see `CHANGELOG_detailed.md` for details. _[Prepared by Claude Code]_
* Eliminated 8 redundant pre-loop parquet writes per year for emission/cbam cost variables by replacing the pre-loop `write_var_df` calls with local dicts (`emission_cost_dfs`, `cbam_cost_dfs`); see `CHANGELOG_detailed.md` for details. _[Prepared by Claude Code]_
* cleaned up code a bit (BTA.py, employment.py, exog_vars.py, scenario.py, tax_rev.py)
* making sure that sectors that go zero production, don't become zombie sectors in the next period (i.e., there variables are zeroed out)
* corrections in ener_balance


## [v0.1.1-alpha] - 2026-03-30

Latest status: running with IPCC regions and custom parameters; baseline is stable up to 2045; cprice scenario is running up to 2045.

### Added

#### Energy

* Cost curves approach have been added for main fuel types (24,25,26,27) -- note there is no data yet for natural gas fuel curves; cost curves determine price and input use (labour and intermediate goods used for production); cost curve sectors are excluded from calibration
* Refining sectors have been set not to have energy efficiency and/or fuel substitution
* Fuel substitution is set to maintain fixed ratio between extraction and "refining" sectors (24-62, 26-63, 27-94), price change (used as a basis for substitution) is weighted average of refining and extraction sector
* Constant fuel consumption for sectors with zero parameters, i.e. if specified parameters are zero than the sector won't have efficiency and/or substitution effects
* Lignite (25) is split from coal as it has different cost curve and different refining structures
* No own substitution, i.e. while the extraction sectors can adjust their use of other energy (i.e. mining use of petrol) they won't substitute to themselves, that's kept constant
* note that `cost_curve` price impacts are being dampened for stability (see `initiate_modules.py` L1247)

#### Household

* "Rebound-effect" added, i.e., endogenous savings feed back to consumption; if endogenous savings are above normal savings rate (defined as average historical for now, but dynamic is implemented, not used) then consumption increases by a factor (see `lambda_save` parameter in household.py)

#### Employment

* Labour constraint calculation has been revised; the new calculation first calculates any losses proportional to initial employment that are coming from a shrinking labour force; then new employment demand is added; new employment is then allocated based on sectoral growth

#### Price formulation

* New calculation of target minimum profit rate; the minimum profit rate such as
```
['profit_rate_min'] = ['interest_rate'] * (1 + ['depreciation_rate'] * ['capital_stock']/['output']) / (1 + ['interest_rate'])
```

#### Technical

* Variable table is the primary location for storing dynamic variables and for exporting results; us the `self.V.write_var` and `self.V.read_var` functions; the variable table includes validation for accepted values
* Variable table writes variables into two formats, for 1D and 2D we use CSV, while for 3D and 4D we use __parquet__, parquet can be read with python or R (use the __arrow__ package in R, the __pyarrow__ in python)
* `WRITE_AT_END` flag has been added, which allows results to be only written at the end of the run cycle (i.e. last year of the simulation)
* calibration method in `calc_fd_vec` has been changed from __L-BFGS__ type minimization to `lsq_linear` based solution; higher efficiency

### Fixed
* 47b8fea13bdaebeb399780d2bf8a58085ba6e8b7
    * correcting current price GDP calculation
    * correcting IO change mechanics
* d12123848c4cc514033ccca81f52aa8880dba631, 29070fa06957cb928dc8a42ffb07671bab91abe4, f5b494677a1fdb8a34fd989c50393d1cc6fe0aa7
    * energy balance / fuel substitution corrections
* 29070fa06957cb928dc8a42ffb07671bab91abe4, 7ceac5acfb049d4227b2199dcb2426826f90442f
    * ctax calculation corrections

---

<!-- Links -->
[Unreleased]: https://github.com/cpmodel/MINDSET_dynamic
[0.1.1-alpha]: https://github.com/cpmodel/MINDSET_dynamic/releases/tag/v0.1.1-alpha