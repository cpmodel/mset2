# -*- coding: utf-8 -*-
"""
Created on Fri Nov 28 11:17:44 2025

Script serves as main interface between MSET and FTT-Power.

@author: hartv, Cormac Lynch
"""

import pandas as pd
import numpy as np
import re
from pathlib import Path
import pickle

# MWIY is in mEUR 2010. Convert to mUSD 2010 (1.33), then to mUSD 2019 (1.17),
# then to th USD 2019 (1000), which is the unit of MSET's investment variables.
FTT_INVESTMENT_TO_TH_USD = 1.33 * 1.17 * 1000

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
    
    
def redistribute_power_fuel_use(cur, prev, growth):
    """Rescale power-sector fuel flows (TJ) to FTT's regional fuel growth.

    Applies FTT's year-on-year growth ratio to last year's regional total then
    splits it across suppliers using MSET's current energy balance supplier 
    shares.
    
    If a region's current flows sum to zero, previous-year shares are used. If
    previous flows are also zero, current values are kept. Regions with a
    missing/NaN growth factor keep their current values.

    Args:
        cur (pd.series): current-year power-sector fuel flows (TJ) 
            indexed by (REG_imp, REG_exp, PROD_COMM, TRAD_COMM)
        prev (pd.series): previous-year power-sector fuel flows (TJ) 
            indexed by (REG_imp, REG_exp, PROD_COMM, TRAD_COMM)
        growth (pd.series): year-on-year growth ratio by importing region
            (1.0 = unchanged), indexed by (REG_imp)
            
    Returns:
        pd.series: rescaled current-year power-sector fuel flows (TJ)

    """
    reg = cur.index.get_level_values('REG_imp').astype(str).to_numpy()
    prev_reg = prev.index.get_level_values('REG_imp').astype(str).to_numpy()
    prev_total = pd.Series(reg).map(prev.groupby(prev_reg).sum()).fillna(0.0).to_numpy()
    prev_aligned = prev.reindex(cur.index).fillna(0.0)
    prev_aligned_total = prev_aligned.groupby(reg).transform('sum').to_numpy()
    cur_total = cur.groupby(reg).transform('sum').to_numpy()

    cur_v = cur.to_numpy(dtype=float)
    prev_v = prev_aligned.to_numpy(dtype=float)
    share = np.where(
        cur_total > 0, np.divide(cur_v, cur_total, out=np.zeros_like(cur_v), 
                                 where=cur_total > 0),
        np.divide(prev_v, prev_aligned_total, out=np.zeros_like(prev_v),
                  where=prev_aligned_total > 0))
    growth_row = pd.Series(reg).map(growth).to_numpy(dtype=float)
    new = np.where(prev_total == 0, cur_v, prev_total * growth_row * share)
    return pd.Series(np.where(np.isnan(growth_row), cur_v, new), 
                     index=cur.index, name=cur.name)


def _get_power_fuel_implicit_prices(V, model_start, sectors):
    """ 
    Retrieve and shape implicit fuel prices (kUSD/TJ) for power-sector fuel
    rows.
    
    Args:
        V (variables_table): used to read fuel_implicit_price variable
        model_start (int): first year of the model run
        sectors (list of int): TRAD_COMM values of power-sector fuel suppliers

    Returns:
        prices (pd.DataFrame): with columns ['REG_imp', 'REG_exp', 'PROD_COMM', 
                'TRAD_COMM', 'fuel_implicit_price']
    """
    var_name = 'fuel_implicit_price'
    table_id = V.empty_tables_table.loc[
        V.empty_tables_table['VAR_NAME'] == var_name, 'id'].values[0]
    index = V.empty_tables[table_id]
    mask = ((index['PROD_COMM'] == 93)
            & index['TRAD_COMM'].isin(sectors)).to_numpy()
    prices = index.loc[mask, ['REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM']].copy()
    prices[var_name] = np.asarray(V.read_var(var_name, model_start))[mask]
    return prices

def solve_year_ftt(self, year, ftt_model, DYNAMIC, Scenario, 
                   ener_base, IO_model, model_start, model_end):
    """Run one year of FTT:Power and feed its results back into MSET.

    Feeds MSET electricity demand, fuel-price changes (after 2019) and
    power-sector carbon prices into FTT, solves FTT for the year, then rescales
    MSET's power-sector fuel flows to FTT's MEPD growth. ``energy_flows`` and
    the matching ``new_IO`` rows are written to the same physical target via the
    implicit fuel prices, keeping next year's ``IND_BASE`` consistent with the
    energy balance.

    Args:
        year (int): Current simulation year.
        ftt_model (MINDSET_FTT_Power.SourceCode.model_class.ModelRun): FTT model run, mutated in place.
        DYNAMIC (dict): Dynamic model state; passed through unchanged.
        Scenario (SourceCode.scenario.scenario): Supplies ``tax_rate`` for carbon prices.
        ener_base (pd.DataFrame): Current-year energy balance (TJ) for electricity demand.
        IO_model (SourceCode.InputOutput.IO): Provides ``IND_BASE`` for fuel-price weights.
        model_start (int): First model year; fuel growth is applied for years after it.
        model_end (int): Last model year; FTT output is pickled in this year.

    Returns:
        tuple: ``(ftt_model, DYNAMIC)``.

    """
    
    ## Initialise with title lengths
    n_reg      = len(ftt_model.titles['RTI'])
    n_tech     = len(ftt_model.titles['T2TI'])
    _rti_short = list(ftt_model.titles['RTI_short'])
    # Get electricity demand and convert TJ to PJ
    elec_dem = ener_base.loc[ener_base.TRAD_COMM == 93].groupby('REG_imp').sum()['fuel_use'] / 1000
    # Calculate FTT year index
    ftt_yr_idx = year - ftt_model.ftt_start
    ftt_scenario = ftt_model.scenarios
    # Get the FTT index of electricity
    elec_idx = ftt_model.titles['JTI'].index('8 Electricity')
    # Assign electricity demand to FTT
    electricity_demand = elec_dem[list(ftt_model.titles['RTI_short'])].values
    ftt_model.input[ftt_scenario]['MEWD'][:, elec_idx, 0, ftt_yr_idx] = electricity_demand
    ftt_model.input[ftt_scenario]['MEWDX'][:, elec_idx, 0, ftt_yr_idx] = electricity_demand
    
    # From 2020 onward, feed MSET's own price signal back into FTT. The
    # per-year change is stored on the model object (_mset_fuel_price_index_change)
    # rather than in the FTT input dict. This is then used in 
    # MINDSET_FTT_Power/model_class.py to update the fuel price index for the year.
    # FPIX is then used in the FTT LCOE equations to scale fuel costs to MSET prices.
    if year > 2019:
        # Monetary fuel purchases (kUSD) by importing region, exporting region,
        # user sector and fuel commodity. Only FTT fuel commodities are needed.
        fuel_purchases = IO_model.IND_BASE.loc[
            IO_model.IND_BASE.index.get_level_values('TRAD_COMM').isin(
                ftt_model.ftt_fuel_converter.TRAD_COMM), 'z_bp'
        ].copy()
        # Year-on-year producer price change (fraction) by producing region/sector.
        price_change = self.V.read_var(
            'delta_price_yoy', year, as_df=True
        ).rename(columns={'delta_price_yoy': 'dp'})
        # Keep only energy-producing sectors represented in FTT.
        energy_price_change = price_change.loc[
            price_change.PROD_COMM.isin(ftt_model.ftt_tech_converter.PROD_COMM)
        ].copy()
        # Match each purchase to its exporter's domestic price change:
        # REG_exp (exporter) <-> REG_imp (producing region in price_change).
        purchases_with_price_change = pd.merge(
            fuel_purchases.reset_index(), energy_price_change,
            left_on='REG_exp', right_on='REG_imp', how='inner',
            suffixes=('', '_y'))

        # One purchase-weighted price change per (importing region, FTT technology).
        fuel_price_change = np.zeros((n_reg, n_tech, 1))

        for ftt_tech, tech_sectors in ftt_model.ftt_tech_converter.groupby('T2TI'):
            tech_price_change = purchases_with_price_change.loc[
                purchases_with_price_change.PROD_COMM.isin(tech_sectors.PROD_COMM)]
            # Weight by kUSD purchases so large trade flows dominate the average.
            import_weighted_dp = (
                tech_price_change.groupby("REG_imp", group_keys=False, dropna=False)
                .apply(
                    lambda g: (g["dp"] * g["z_bp"]).sum() / g["z_bp"].sum()
                    if g["z_bp"].sum() != 0
                    else 0,
                    include_groups=False))
            tech_position = ftt_model.titles['T2TI'].index(ftt_tech)
            import_weighted_dp = import_weighted_dp.reindex(_rti_short).fillna(0.0)
            fuel_price_change[:, tech_position, 0] = import_weighted_dp.values

        ftt_model._mset_fuel_price_index_change = fuel_price_change
        
    # Carbon price: per-(region, technology) ctax in EUR2015/tCO2.
    # model_class.solve_year() applies the EUR2015→USD2013 conversion using current-year FTT exchange-rate variables.
    c_price_power = Scenario.tax_rate.loc[Scenario.tax_rate.PROD_COMM == 93].copy()
    reppx_arr = np.zeros((n_reg, n_tech, 1))
    # Fuel-to-technology index mapping is cached on ftt_model at init (model_class.py); static across years.
    for fuel, sectors in ftt_model.ftt_fuel_converter.groupby('ERTI'):
        if fuel not in ftt_model.fuel_to_tech_idxs:
            continue
        sec_c_price = c_price_power.loc[c_price_power.TRAD_COMM.isin(sectors.TRAD_COMM)]
        if len(sec_c_price) == 0:
            continue
        avg_by_reg = sec_c_price.groupby('REG_imp')['ctax'].mean()
        for tech_idx in ftt_model.fuel_to_tech_idxs[fuel]:
            for reg_idx, reg_short in enumerate(_rti_short):
                if reg_short in avg_by_reg.index:
                    reppx_arr[reg_idx, tech_idx, 0] = avg_by_reg[reg_short]
    if np.any(reppx_arr != 0):
        ftt_model._mset_reppx = reppx_arr
    # else: leave _mset_reppx as None → CO2taxP stays zero (correct for no-tax years)
    
    # Solve year
    ftt_model.variables, ftt_model.lags = ftt_model.solve_year(
        year, ftt_yr_idx, ftt_model.scenarios
        )
    
    # Populate output container
    for var in ftt_model.variables:
        if 'TIME' in ftt_model.dims[var]:
            ftt_model.output[ftt_model.scenarios][var][:, :, :, ftt_yr_idx] = ftt_model.variables[var]
        else:
            ftt_model.output[ftt_model.scenarios][var][:, :, :, 0] = ftt_model.variables[var]
    
    # Rescale MSET's power-sector fuel flows using FTT's year-on-year fuel
    # demand growth. The previous year is needed for both FTT's growth ratio and
    # MSET's previous supplier split.
    if year > model_start:
        # Previous-year energy_flows; supplies the previous supplier split below.
        energy_flows_prev = self.V.read_var_df('energy_flows', year - 1)
        # Keep only previous-year power-sector flows.
        power_energy_prev = energy_flows_prev.loc[energy_flows_prev.PROD_COMM == 93].copy()
        # FTT primary energy demand (MEPD) for the current and previous year.
        ftt_energy_dem = ftt_model.output[ftt_model.scenarios]['MEPD'][:, :, 0, ftt_yr_idx]
        ftt_energy_dem_prev = ftt_model.output[ftt_model.scenarios]['MEPD'][:, :, 0, ftt_yr_idx - 1]
        # Read energy_flows once before the loop; all sector updates are applied in-place,
        # then written back once after the loop (avoids N reads+writes for N fuel sectors).
        energy_flows = self.V.read_var_df('energy_flows', year).set_index(['REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM']).sort_index()
        ftt_fuel_sectors = set()  # TRAD_COMM values whose power-sector flows FTT updates
        # Loop over supplying sectors (skip TRAD_COMM=93: renewables/nuclear have no
        # fuel commodity input; including them corrupts the electricity demand fed back to FTT)
        for sector, fuels in ftt_model.ftt_fuel_converter.groupby('TRAD_COMM'):
            if sector == 93:
                continue
            # MEPD columns for the FTT fuels supplied by this MSET sector.
            fuel_idx = [ftt_model.titles['ERTI'].index(f) for f in fuels.ERTI]
            # FTT fuel demand for this sector, current and previous year, then growth by region.
            fuel_demand = ftt_energy_dem[:, fuel_idx].sum(axis = 1)
            fuel_demand_prev = ftt_energy_dem_prev[:, fuel_idx].sum(axis = 1)
            fuel_demand_growth = np.divide(fuel_demand, fuel_demand_prev,
                                           out=np.ones_like(fuel_demand),
                                           where=fuel_demand_prev!=0)
            fuel_demand_growth = pd.Series(fuel_demand_growth, index = ftt_model.titles['RTI_short'])
            # Previous-year flows and supplier split for this fuel.
            power_energy_prev_sector = power_energy_prev.loc[power_energy_prev.TRAD_COMM == sector].copy()
            power_energy_prev_sector['PROD_COMM'] = power_energy_prev_sector['PROD_COMM'].astype(int)
            power_energy_prev_sector['TRAD_COMM'] = power_energy_prev_sector['TRAD_COMM'].astype(int)
            prev_supplier_split = power_energy_prev_sector.set_index(
                ['REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM'])['fuel_use']
            # Current-year power-sector rows for this fuel (MSET's updated supplier split)
            _is_sec = ((energy_flows.index.get_level_values('PROD_COMM') == 93)
                       & (energy_flows.index.get_level_values('TRAD_COMM') == sector))
            if not _is_sec.any():
                continue
            ftt_fuel_sectors.add(sector)
            energy_flows.loc[_is_sec, 'fuel_use'] = redistribute_power_fuel_use(
                energy_flows.loc[_is_sec, 'fuel_use'], prev_supplier_split, fuel_demand_growth).to_numpy()
        # Single write after all sector updates are applied
        self.V.write_var_df('energy_flows', year, energy_flows.reset_index())
       
        # Write FTT's fuel mix back into new_IO for the power sector so the
        # monetary IO and the energy balance cannot drift apart. new_IO[year] was
        # built by model_class.py before FTT ran; these z_bp/a_bp values become
        # next year's IND_BASE via the roll-forward in initiate_modules.py.
        # z_bp is the monetary intermediate flow (kUSD); a_bp =
        # z_bp / output is the input coefficient; a_tech is the total input
        # coefficient summed across exporters.
        # TRAD_COMM=93 (electricity/renewables) is excluded by the continue above.
        if ftt_fuel_sectors:
            new_io = self.V.read_var_df('new_IO', year)
            power_rows = new_io['PROD_COMM'] == 93
            power_fuel_rows = power_rows & new_io['TRAD_COMM'].isin(ftt_fuel_sectors)
            flow_key = pd.MultiIndex.from_frame(
                new_io.loc[power_fuel_rows, ['REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM']])
            # Physical targets FTT just wrote to energy_flows, reindexed onto new_IO rows.
            physical_target = energy_flows['fuel_use'].reindex(flow_key)
            implicit_prices = _get_power_fuel_implicit_prices(
                self.V, model_start, ftt_fuel_sectors)
            implicit_price = (
                implicit_prices.set_index(
                    ['REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM'])['fuel_implicit_price']
                .reindex(flow_key)
            )
            # Only overwrite rows with both a physical target and a price.
            has_valid_target = (physical_target.notna() & implicit_price.notna()).to_numpy()
            monetary_flow = (physical_target.fillna(0.0).to_numpy()
                             * implicit_price.fillna(0.0).to_numpy())
            new_io.loc[power_fuel_rows, 'z_bp'] = np.where(
                has_valid_target, monetary_flow,
                new_io.loc[power_fuel_rows, 'z_bp'].to_numpy())
            # Recompute a_bp = z_bp / output for the rows whose z_bp changed.
            # Zero output implies an undefined coefficient, so keep a_bp at zero.
            row_output = new_io.loc[power_fuel_rows, 'output'].to_numpy()
            new_io.loc[power_fuel_rows, 'a_bp'] = np.divide(
                new_io.loc[power_fuel_rows, 'z_bp'].to_numpy(), row_output,
                out=np.zeros_like(row_output, dtype=float),
                where=row_output != 0)

            # a_tech sums a_bp across exporters, giving the total (domestic +
            # imported) fuel input coefficient. Refresh every power row because
            # any power-fuel a_bp may have changed.
            new_io.loc[power_rows, 'a_tech'] = (
                new_io[power_rows]
                .groupby(['REG_imp', 'TRAD_COMM', 'PROD_COMM'])['a_bp']
                .transform('sum')
            )

            # Save the updated IO table; next year's IND_BASE takes from this.
            self.V.write_var_df('new_IO', year, new_io)
    
    # Map FTT's technology-level investment (MWIY, mEUR 2010) to MRIO sectors
    # via ftt_inv_converter, so MSET can use it in its investment module.
    ftt_model.investment[year] = ftt_investment_by_mrio_sector(ftt_model, ftt_yr_idx)
    # Convert mEUR 2010 to th USD 2019 (MSET investment units).
    ftt_model.investment[year] = ftt_model.investment[year] * FTT_INVESTMENT_TO_TH_USD

    # Export results in the last year
    if year == model_end:
        output_dir = Path('.') / 'MINDSET_FTT_Power' / 'Output'
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / 'Results.pickle', 'wb') as f:
            pickle.dump(ftt_model.output, f)
            
    return ftt_model, DYNAMIC