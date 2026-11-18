# -*- coding: utf-8 -*-
"""
Created on Fri Nov 28 11:17:44 2025

Script serves as main interface between MSET and FTT-Power.

@author: hartv
"""

import pandas as pd
import numpy as np
import re
from pathlib import Path
import pickle

# MWIY is in mUSD(2023). Convert to th USD 2019, the unit of MSET's investment variables.
# CPI taken from US Bureau of Labor Statistics, CPI for All Urban Consumers (CPI-U)
FTT_INVESTMENT_TO_TH_USD = (255.657 / 304.702) * 1000

def _per_unit_growth(x_t, x_t0, gen_t, gen_t0):
    """Relative change of x per unit of total generation: (x_t/gen_t)/(x_t0/gen_t0) - 1.

    x has regions on axis 0 (1-D, or 2-D with commodities on axis 1); gen is (n_reg,).
    Dividing out total generation keeps FTT's demand-driven growth out of the signal: MSET's
    IO solve already scales sector 93's inputs with its output, so only the mix effect is
    applied to the coefficients. Returns 0 where the ratio is undefined.
    """
    shape = (-1,) + (1,) * (np.ndim(x_t) - 1)
    gen_t0 = np.reshape(gen_t0, shape)
    num = x_t * gen_t0
    den = x_t0 * np.reshape(gen_t, shape)
    return np.divide(num, den, out=np.ones_like(num, dtype=float), where=(den != 0) & (gen_t0 != 0)) - 1.0


def _normalise_t2ti_name(name):
    """Remove a leading numeric label and separator from an FTT technology name."""
    return re.sub(r'^\s*\d+\s*[.\-:]?\s*', '', str(name))

def ftt_investment_by_mrio_sector(ftt_model, ftt_yr_idx):
    """
    Map FTT's MWIY (investment by technology) to MRIO sectors via
    ftt_inv_converter.

    Args:
        ftt_model (FTT model): The FTT model object
        ftt_yr_idx (int): index of the current year in FTT's time dimension

    Returns:
        investment_by_mrio_sector (np.ndarray): array of shape (n_reg, n_mrio_sectors)

    """
    investment_by_tech = ftt_model.output[ftt_model.scenarios]['MWIY'][:, :, 0, ftt_yr_idx]
    converter_cols = list(ftt_model.ftt_inv_converter.columns)
    converter_keys = [_normalise_t2ti_name(name) for name in converter_cols]
    title_keys = [_normalise_t2ti_name(name) for name in ftt_model.titles['T2TI']]

    if len(set(title_keys)) != len(title_keys):
        raise ValueError(f"Duplicate T2TI titles after normalisation: {title_keys}")
    if len(set(converter_keys)) != len(converter_keys):
        raise ValueError(f"Duplicate converter columns after normalisation: {converter_keys}")

    # Check that all converter columns are present in T2TI titles
    missing = sorted(set(converter_keys) - set(title_keys))
    if missing:
        raise ValueError(f"FTT investment converter columns missing from T2TI titles: {missing}")

    investment_by_mrio_sector = (
        pd.DataFrame(investment_by_tech, columns=title_keys)[converter_keys].to_numpy()
    )
    return (np.array(ftt_model.ftt_inv_converter)[np.newaxis, :, :] *
            investment_by_mrio_sector[:, np.newaxis, :]).sum(axis=2)

def set_electricity_demand(ftt_model, ener_base, ftt_yr_idx, region_codes):
    """Write MSET electricity demand to FTT's MEWD and MEWDX inputs in PJ.

    Args:
        ftt_model: FTT model whose inputs are updated in place.
        ener_base (pd.DataFrame): Current-year energy balance in TJ.
        ftt_yr_idx (int): Current year index in FTT's time dimension.
        region_codes (list): FTT region codes in output-array order.
    """
    # Get electricity demand and convert TJ to PJ
    elec_demand_pj = (
        ener_base.loc[ener_base.TRAD_COMM == 93]
        .groupby('REG_imp')
        .sum()['fuel_use'] / 1000
    )
    ftt_scenario = ftt_model.scenarios
    # Get the index of electricity
    elec_idx = ftt_model.titles['JTI'].index('8 Electricity')
    # Assign electricity demand to FTT
    elec_demand_vals = elec_demand_pj[region_codes].values
    ftt_model.input[ftt_scenario]['MEWD'][:, elec_idx, 0, ftt_yr_idx] = elec_demand_vals
    ftt_model.input[ftt_scenario]['MEWDX'][:, elec_idx, 0, ftt_yr_idx] = elec_demand_vals



def set_fuel_price_changes(self, year, ftt_model, IO_model,
                            n_regions, n_techs, region_codes):
    """Set trade-weighted fuel-price changes on the FTT model after 2019.

    The signal is consumed by FTT only when FPIX is present in its variables.

    Args:
        self: MSET model providing price changes through its variable table.
        year (int): Current simulation year.
        ftt_model: FTT model receiving the price-change array.
        IO_model: Input-output model providing trade-flow weights in IND_BASE.
        n_regions (int): Number of FTT regions.
        n_techs (int): Number of FTT technologies.
        region_codes (list): FTT region codes in output-array order.

    """

    # fuel_price_index_change is stored on the model object (_mset_fuel_price_index_change)
    # rather than in the FTT input dict, so no change to FTT_Standalone's VariableListing.csv
    # is needed. model_class.py converts _mset_fuel_price_index_change to FPIX and injects it
    # into variables before calling ftt_p_solve each year.
    if year > 2019:
        # Assess price changes by FTT fuels.
        # delta_price_yoy contains year-on-year price changes.
        # z_bp weights exporter price changes when aggregating by importing region.
        fuel_trade_flows = IO_model.IND_BASE.loc[
            IO_model.IND_BASE.index.get_level_values('TRAD_COMM').isin(
                ftt_model.ftt_fuel_converter.TRAD_COMM),'z_bp'].copy()
        domestic_price_changes = self.V.read_var(
            'delta_price_yoy', year, as_df=True
        ).rename(columns={'delta_price_yoy': 'dp'})
        fuel_price_changes_by_exporter = domestic_price_changes.loc[
            domestic_price_changes.PROD_COMM.isin(ftt_model.ftt_tech_converter.PROD_COMM)
        ].copy()
        merged_fuel_prices = pd.merge(
            fuel_trade_flows.reset_index(),
            fuel_price_changes_by_exporter,
            left_on='REG_exp',
            right_on='REG_imp',
            how='inner',
            suffixes=('', '_y')
        )

        # Year-on-year fractional change in fuel price per (region, T2TI technology); feeds FTT's cumulative FPIX.
        fuel_price_index_change = np.zeros((n_regions, n_techs, 1))

        for tech, sectors in ftt_model.ftt_tech_converter.groupby('T2TI'):
            sector_price_changes = merged_fuel_prices.loc[
                merged_fuel_prices.PROD_COMM.isin(sectors.PROD_COMM)
            ]
            weighted_price_change = (
                sector_price_changes.groupby("REG_imp", group_keys=False, dropna=False)
                .apply(
                    lambda g: (g["dp"] * g["z_bp"]).sum() / g["z_bp"].sum()
                    if g["z_bp"].sum() != 0
                    else 0,
                    include_groups=False
                )
            )
            technology_idx = ftt_model.titles['T2TI'].index(tech)
            weighted_price_change = weighted_price_change.reindex(region_codes).fillna(0.0)
            fuel_price_index_change[:, technology_idx, 0] = weighted_price_change.values

        ftt_model._mset_fuel_price_index_change = fuel_price_index_change



def set_carbon_prices(ftt_model, Scenario, n_regions, n_techs, region_codes):
    """Map MSET power-sector carbon prices to FTT regions and technologies.

    A nonzero mapping is stored on the FTT model; an all-zero mapping leaves
    any existing override unchanged.

    Args:
        ftt_model: FTT model receiving the carbon-price array.
        Scenario: Scenario providing carbon prices in tax_rate.
        n_regions (int): Number of FTT regions.
        n_techs (int): Number of FTT technologies.
        region_codes (list): FTT region codes in output-array order.
    """

    # Carbon price: per-(region, technology) ctax in EUR2015/tCO2.
    # model_class.solve_year() applies the EUR2015→USD2013 conversion using current-year FTT exchange-rate variables.
    power_carbon_prices = Scenario.tax_rate.loc[Scenario.tax_rate.PROD_COMM == 93].copy()
    reppx_array = np.zeros((n_regions, n_techs, 1))
    # Fuel-to-technology index mapping is cached on ftt_model at init (model_class.py); static across years.
    for fuel_type, sectors in ftt_model.ftt_fuel_converter.groupby('ERTI'):
        if fuel_type not in ftt_model.fuel_to_tech_idxs:
            continue
        sector_carbon_prices = power_carbon_prices.loc[
            power_carbon_prices.TRAD_COMM.isin(sectors.TRAD_COMM)
        ]
        if len(sector_carbon_prices) == 0:
            continue
        avg_carbon_price_by_region = sector_carbon_prices.groupby('REG_imp')['ctax'].mean()
        for technology_idx in ftt_model.fuel_to_tech_idxs[fuel_type]:
            for region_idx, region_code in enumerate(region_codes):
                if region_code in avg_carbon_price_by_region.index:
                    reppx_array[region_idx, technology_idx, 0] = (
                        avg_carbon_price_by_region[region_code]
                    )
    # If the mapped prices are all zero, leave _mset_reppx unset (no MSET override).
    if np.any(reppx_array != 0):
        ftt_model._mset_reppx = reppx_array


def apply_fuel_demand_feedback(self, year, ftt_model, ftt_yr_idx,
                                model_start, region_codes):
    """Apply FTT fuel-demand growth and queue IO and employment feedback for MSET.

    No feedback is applied in the first model year. Later years use previous
    energy flows and FTT MEPD growth, excluding electricity as an input fuel.
    IO and employment feedback are queued for MSET to apply in the following year.

    Args:
        self: MSET model whose variable table is updated in place.
        year (int): Current simulation year.
        ftt_model: FTT model providing current and previous MEPD output.
        ftt_yr_idx (int): Current year index in FTT's time dimension.
        model_start (int): First model year.
        region_codes (list): FTT region codes in output-array order.
    """
    # Update power-sector fuel flows after the first model year using FTT growth.
    # Use the previous year's FTT energy demand as the growth baseline.
    if year > model_start:
        # Take energy demand from previous year
        previous_yr_energy_flows = self.V.read_var_df('energy_flows', year - 1)
        # Filter on power sector
        previous_power_energy_flows = previous_yr_energy_flows.loc[
            previous_yr_energy_flows.PROD_COMM == 93
        ].copy()
        # Get FTT's current and previous primary-energy demand and generation.
        current_ftt_energy_demand = ftt_model.output[ftt_model.scenarios]['MEPD'][:, :, 0, ftt_yr_idx]
        previous_ftt_energy_demand = ftt_model.output[ftt_model.scenarios]['MEPD'][:, :, 0, ftt_yr_idx - 1]
        mewg_t = ftt_model.output[ftt_model.scenarios]['MEWG'][:, :, 0, ftt_yr_idx]
        mewg_t0 = ftt_model.output[ftt_model.scenarios]['MEWG'][:, :, 0, ftt_yr_idx - 1]
        gen_t, gen_t0 = mewg_t.sum(axis=1), mewg_t0.sum(axis=1)
        # Read current-year energy_flows once, apply all sector updates in place,
        # and write the table once after the loop.
        energy_flows_by_idx = (
            self.V.read_var_df('energy_flows', year)
            .set_index(['REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM'])
            .sort_index()
        )
        fuel_demand_growth_by_sector = {}
        fuel_mix_growth_by_sector = {}
        # Skip TRAD_COMM=93 so electricity itself is not treated as an input-fuel
        # category in the FTT growth feedback.
        for sector, fuels in ftt_model.ftt_fuel_converter.groupby('TRAD_COMM'):
            if sector == 93:
                continue
            # Get indices of corresponding fuels
            fuel_indices = [
                ftt_model.titles['ERTI'].index(fuel_code)
                for fuel_code in fuels.ERTI
            ]
            # Get fuel demand for the given sectors
            current_fuel_demand = current_ftt_energy_demand[:, fuel_indices].sum(axis = 1)
            previous_fuel_demand = previous_ftt_energy_demand[:, fuel_indices].sum(axis = 1)
            # Scale MSET's physical fuel use by FTT's level-demand growth.
            fuel_demand_growth = np.divide(current_fuel_demand, previous_fuel_demand,
                                           out=np.ones_like(current_fuel_demand),
                                           where=previous_fuel_demand != 0)
            fuel_demand_growth = pd.Series(fuel_demand_growth, index=region_codes)
            fuel_demand_growth_by_sector[sector] = fuel_demand_growth
            # IO feedback removes total-generation growth, which the IO solve already captures.
            fuel_mix_growth_by_sector[sector] = pd.Series(
                1.0 + _per_unit_growth(
                    current_fuel_demand, previous_fuel_demand, gen_t, gen_t0
                ),
                index=region_codes,
            )
            # Use prior-year power-sector flows as the baseline for this sector's growth update.
            power_energy_flows_for_sector = previous_power_energy_flows.loc[
                previous_power_energy_flows.TRAD_COMM == sector
            ].copy()

            power_energy_flows_for_sector["growth"] = (
                power_energy_flows_for_sector["REG_imp"].map(fuel_demand_growth)
            )
            power_energy_flows_for_sector["fuel_use"] = (
                power_energy_flows_for_sector["fuel_use"]
                * power_energy_flows_for_sector["growth"]
            )
            power_energy_flows_for_sector = power_energy_flows_for_sector.drop(columns=['growth'])
            power_energy_flows_for_sector['PROD_COMM'] = power_energy_flows_for_sector['PROD_COMM'].astype(int)
            power_energy_flows_for_sector['TRAD_COMM'] = power_energy_flows_for_sector['TRAD_COMM'].astype(int)
            power_energy_flows_for_sector = power_energy_flows_for_sector.set_index(
                ['REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM']
            )
            # Accumulate updates; write the complete energy_flows table after processing all sectors.
            energy_flows_by_idx.update(power_energy_flows_for_sector)
        # Single write after all sector updates are applied
        self.V.write_var_df('energy_flows', year, energy_flows_by_idx.reset_index())
        # Defer the FTT->MSET fuel-mix signal to ftt_model; initiate_modules.py
        # applies it in the following year. The first FTT transition is skipped:
        # t-1 is FTT's init state, not a real observation.
        _io_mode = ftt_model.ftt_power_io_mode

        if ftt_yr_idx == 1:
            ftt_model._mset_pending_fuel_io_impact = None
        elif _io_mode == 'tech_matrix':
            # (A_elec @ MEWG_t / sum MEWG_t) / (A_elec @ MEWG_t-1 / sum MEWG_t-1) - 1,
            # per (region, GLORIA commodity)
            A_elec = ftt_model.ftt_cefio_a_elec
            Ax_t  = mewg_t  @ A_elec.T.values
            Ax_t0 = mewg_t0 @ A_elec.T.values
            _delta_tm = _per_unit_growth(Ax_t, Ax_t0, gen_t, gen_t0)
            # Keep commodities with a non-zero recipe; optionally drop the power sector's own
            # row (TRAD_COMM=93) to avoid a self-referential feedback.
            _codes = A_elec.index.to_numpy().astype(int)
            _keep = (A_elec.values != 0).any(axis=1)
            if ftt_model.ftt_tech_matrix_exclude_own_sector:
                _keep &= _codes != 93
            ftt_model._mset_pending_fuel_io_impact = (
                pd.DataFrame(_delta_tm[:, _keep], index=region_codes, columns=_codes[_keep])
                .rename_axis(index='REG_imp', columns='TRAD_COMM')
                .stack()
                .rename('fuel_change_relative')
                .reset_index()
            )
        else:
            _rows = []
            for _sector, _growth in fuel_mix_growth_by_sector.items():
                _relative_change = _growth - 1.0
                _rows.append(pd.DataFrame({
                    'REG_imp': _relative_change.index,
                    'TRAD_COMM': int(_sector),
                    'fuel_change_relative': _relative_change.values,
                }))
            ftt_model._mset_pending_fuel_io_impact = (
                pd.concat(_rows, ignore_index=True) if _rows
                else pd.DataFrame(columns=['REG_imp', 'TRAD_COMM', 'fuel_change_relative'])
            )

        # FTT-driven labour-intensity growth signal for PROD_COMM=93, composed into
        # MSET's employment growth rate next year. tech_matrix mode only.
        _empl_coupling = ftt_model.ftt_employment_coupling
        _l_elec = getattr(ftt_model, 'ftt_labour_intensity', None)
        if ftt_yr_idx == 1 or not _empl_coupling or _l_elec is None:
            ftt_model._mset_pending_employment_impact = None
        else:
            l_vec = _l_elec.reindex(list(ftt_model.titles['T2TI'])).fillna(0.0).values
            Lx_t  = mewg_t  @ l_vec
            Lx_t0 = mewg_t0 @ l_vec
            _delta_n_ftt = _per_unit_growth(Lx_t, Lx_t0, gen_t, gen_t0)
            _relative_change = pd.Series(_delta_n_ftt, index=region_codes)
            ftt_model._mset_pending_employment_impact = pd.DataFrame({
                'REG_imp': _relative_change.index,
                'PROD_COMM': 93,
                'employment_change_relative': _relative_change.values,
            })


def run_ftt_year(self, year, ftt_model, Scenario, ener_base,
                 IO_model, model_start, model_end):
    """Run one year of FTT:Power and feed its results back into MSET.

    Feeds MSET electricity demand, fuel-price changes (after 2019), and
    power-sector carbon prices into FTT. FTT results are then used to update
    MSET's power-sector fuel flows and queue IO and employment feedback for
    MSET to apply in the following year.

    Args:
        year (int): Current simulation year.
        ftt_model (MINDSET_FTT_Power.SourceCode.model_class.ModelRun): FTT model run, mutated in place.
        Scenario (SourceCode.scenario.scenario): Supplies ``tax_rate`` for carbon prices.
        ener_base (pd.DataFrame): Current-year energy balance (TJ) for electricity demand.
        IO_model (SourceCode.InputOutput.IO): Provides ``IND_BASE`` for fuel-price weights.
        model_start (int): First model year; fuel feedback is applied for later years.
        model_end (int): Last model year; FTT output is pickled in this year.

    Returns:
        ftt_model: The updated FTT model.

    """
    n_regions = len(ftt_model.titles['RTI'])
    n_techs = len(ftt_model.titles['T2TI'])
    region_codes = list(ftt_model.titles['RTI_short'])
    ftt_yr_idx = year - ftt_model.ftt_start

    set_electricity_demand(ftt_model, ener_base, ftt_yr_idx, region_codes)
    set_fuel_price_changes(
        self, year, ftt_model, IO_model, n_regions, n_techs, region_codes
    )
    set_carbon_prices(ftt_model, Scenario, n_regions, n_techs, region_codes)

    # Solve FTT for the current year and store results in ftt_model.output
    ftt_model.variables, ftt_model.lags = ftt_model.solve_year(
        year, ftt_yr_idx, ftt_model.scenarios
    )
    for variable_name in ftt_model.variables:
        if 'TIME' in ftt_model.dims[variable_name]:
            ftt_model.output[ftt_model.scenarios][variable_name][
                :, :, :, ftt_yr_idx
            ] = ftt_model.variables[variable_name]
        else:
            ftt_model.output[ftt_model.scenarios][variable_name][
                :, :, :, 0
            ] = ftt_model.variables[variable_name]

    apply_fuel_demand_feedback(
        self, year, ftt_model, ftt_yr_idx, model_start, region_codes
    )

    # Assess investment
    ftt_model.investment[year] = ftt_investment_by_mrio_sector(ftt_model, ftt_yr_idx)
    # Convert mUSD 2023 to th USD 2019 (MSET investment units)
    ftt_model.investment[year] = ftt_model.investment[year] * FTT_INVESTMENT_TO_TH_USD

    # Export results in the last year
    if year == model_end:
        output_dir = Path('.') / 'MINDSET_FTT_Power' / 'Output'
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / 'Results.pickle', 'wb') as results_file:
            pickle.dump(ftt_model.output, results_file)

    return ftt_model