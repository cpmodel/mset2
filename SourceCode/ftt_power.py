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

def solve_year_ftt(self, year, ftt_model, Scenario, ener_base,
                   IO_model, model_start, model_end):
    """Run one year of FTT:Power and feed its results back into MSET.

    Feeds MSET electricity demand, fuel-price changes (after 2019), and
    power-sector carbon prices into FTT, then rescales MSET's power-sector fuel
    flows using year-on-year FTT MEPD growth. The same growth factors are
    applied to matching ``new_IO`` rows; that updated IO table is carried
    forward as the following year's ``IND_BASE``.

    Args:
        year (int): Current simulation year.
        ftt_model (MINDSET_FTT_Power.SourceCode.model_class.ModelRun): FTT model run, mutated in place.
        Scenario (SourceCode.scenario.scenario): Supplies ``tax_rate`` for carbon prices.
        ener_base (pd.DataFrame): Current-year energy balance (TJ) for electricity demand.
        IO_model (SourceCode.InputOutput.IO): Provides ``IND_BASE`` for fuel-price weights.
        model_start (int): First model year; fuel growth is applied for years after it.
        model_end (int): Last model year; FTT output is pickled in this year.

    Returns:
        ftt_model: The updated FTT model.

    """
    
    # Get number of regions and technologies
    n_regions = len(ftt_model.titles['RTI'])
    n_techs = len(ftt_model.titles['T2TI'])
    region_codes = list(ftt_model.titles['RTI_short'])
    # Get electricity demand and convert TJ to PJ
    elec_demand_pj = (
        ener_base.loc[ener_base.TRAD_COMM == 93]
        .groupby('REG_imp')
        .sum()['fuel_use'] / 1000
    )
    # Calculate FTT year index
    ftt_yr_idx = year - ftt_model.ftt_start
    ftt_scenario = ftt_model.scenarios
    # Get the index of electricity
    elec_idx = ftt_model.titles['JTI'].index('8 Electricity')
    # Assign electricity demand to FTT
    elec_demand_vals = elec_demand_pj[list(ftt_model.titles['RTI_short'])].values
    ftt_model.input[ftt_scenario]['MEWD'][:, elec_idx, 0, ftt_yr_idx] = elec_demand_vals
    ftt_model.input[ftt_scenario]['MEWDX'][:, elec_idx, 0, ftt_yr_idx] = elec_demand_vals
    
    # Supply MSET-estimated fuel-price changes to FTT after 2019.
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
    if np.any(reppx_array != 0):
        ftt_model._mset_reppx = reppx_array
    # If the mapped prices are all zero, leave _mset_reppx unset (no MSET override).
    # Solve year
    ftt_model.variables, ftt_model.lags = ftt_model.solve_year(
        year, ftt_yr_idx, ftt_model.scenarios
    )
    # Populate output container
    for variable_name in ftt_model.variables:
        if 'TIME' in ftt_model.dims[variable_name]:
            ftt_model.output[ftt_model.scenarios][variable_name][
                :, :, :, ftt_yr_idx
            ] = ftt_model.variables[variable_name]
        else:
            ftt_model.output[ftt_model.scenarios][variable_name][
                :, :, :, 0
            ] = ftt_model.variables[variable_name]
    # Update power-sector fuel flows after the first model year using FTT growth.
    # Use the previous year's FTT energy demand as the growth baseline.
    if year > model_start:
        # Take energy demand from previous year
        previous_yr_energy_flows = self.V.read_var_df('energy_flows', year - 1)
        # Filter on power sector
        previous_power_energy_flows = previous_yr_energy_flows.loc[
            previous_yr_energy_flows.PROD_COMM == 93
        ].copy()
        # Get primary energy demand values for t and t-1
        current_ftt_energy_demand = ftt_model.output[ftt_model.scenarios]['MEPD'][:, :, 0, ftt_yr_idx]
        previous_ftt_energy_demand = ftt_model.output[ftt_model.scenarios]['MEPD'][:, :, 0, ftt_yr_idx - 1]
        # Read current-year energy_flows once, apply all sector updates in place,
        # and write the table once after the loop.
        energy_flows_by_idx = (
            self.V.read_var_df('energy_flows', year)
            .set_index(['REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM'])
            .sort_index()
        )
        fuel_demand_growth_by_sector = {}  # TRAD_COMM -> pd.Series(growth_ratio, index=RTI_short)
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
            # Calculate growth
            fuel_demand_growth = np.divide(current_fuel_demand, previous_fuel_demand,
                                           out=np.ones_like(current_fuel_demand),
                                           where=previous_fuel_demand != 0)
            fuel_demand_growth = pd.Series(fuel_demand_growth, index=ftt_model.titles['RTI_short'])
            fuel_demand_growth_by_sector[sector] = fuel_demand_growth
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
        # Propagate FTT fuel-mix signal into new_IO for the power sector (PROD_COMM=93).
        # new_IO[year] was written by model_class.py (A_iochange × output) before FTT runs.
        # Apply FTT's MEPD-based growth ratios to the power-sector fuel input rows
        # (TRAD_COMM=93 is already excluded from fuel_demand_growth_by_sector above).
        # These updated z_bp / a_bp values become next year's IND_BASE via the
        # new_IO → IND_BASE roll-forward (initiate_modules.py:50).
        if fuel_demand_growth_by_sector:
            new_io = self.V.read_var_df('new_IO', year)
            power_sector_rows = new_io['PROD_COMM'] == 93
            power_fuel_rows = (
                power_sector_rows
                & new_io['TRAD_COMM'].isin(fuel_demand_growth_by_sector)
            )
            for sector_id, growth_by_region in fuel_demand_growth_by_sector.items():
                sector_rows = power_sector_rows & (new_io['TRAD_COMM'] == sector_id)
                if sector_rows.any():
                    new_io.loc[sector_rows, 'z_bp'] *= (
                        new_io.loc[sector_rows, 'REG_imp']
                        .astype(str)
                        .map(growth_by_region)
                        .fillna(1.0)
                    )
            # Recompute a_bp for the rows we changed, then a_tech for all power rows.
            new_io.loc[power_fuel_rows, 'a_bp'] = np.where(
                new_io.loc[power_fuel_rows, 'output'] != 0,
                new_io.loc[power_fuel_rows, 'z_bp']
                / new_io.loc[power_fuel_rows, 'output'],
                0.0
            )
            new_io.loc[power_sector_rows, 'a_tech'] = (
                new_io[power_sector_rows]
                .groupby(['REG_imp', 'TRAD_COMM', 'PROD_COMM'])['a_bp']
                .transform('sum')
            )
            self.V.write_var_df('new_IO', year, new_io)
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