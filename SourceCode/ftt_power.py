# -*- coding: utf-8 -*-
"""
Created on Fri Nov 28 11:17:44 2025

@author: hartv
"""

import pandas as pd
import numpy as np
import datetime
from pathlib import Path
import json
import pickle

def ftt_investment_by_mrio_sector(ftt_model, y):
    """Map FTT's MWIY (investment by technology) to MRIO sectors via ftt_inv_converter."""
    investment_by_tech = ftt_model.output[ftt_model.scenarios]['MWIY'][:, :, 0, y]
    investment_by_mrio_sector = (
        pd.DataFrame(investment_by_tech, columns=list(ftt_model.titles['T2TI']))
          .reindex(columns=list(ftt_model.ftt_inv_converter.columns)).values
    )
    return (np.array(ftt_model.ftt_inv_converter)[np.newaxis, :, :] *
            investment_by_mrio_sector[:, np.newaxis, :]).sum(axis=2)

def solve_year_ftt(self, year, ftt_model, DYNAMIC, Scenario, ener_base, IO_model, model_start, model_end):
    
    ## FTT: Power
    n_reg      = len(ftt_model.titles['RTI'])
    n_tech     = len(ftt_model.titles['T2TI'])
    _rti_short = list(ftt_model.titles['RTI_short'])
    # Get electricity demand and convert TJ to PJ
    elec_dem = ener_base.loc[ener_base.TRAD_COMM == 93].groupby('REG_imp').sum()['fuel_use'] / 1000
    # Calculate FTT year index
    y = year - ftt_model.ftt_start
    # Get the index of electricity
    elec_idx = ftt_model.titles['JTI'].index('8 Electricity')
    # Assign electricity demand to FTT
    ftt_model.input['S0']['MEWD'][:, elec_idx, 0, y]  = elec_dem[list(ftt_model.titles['RTI_short'])].values
    ftt_model.input['S0']['MEWDX'][:, elec_idx, 0, y] = elec_dem[list(ftt_model.titles['RTI_short'])].values
    # Overwrite fuel price index after 2019, when price changes are estimated in MINDSET.
    # fuel_price_index_change is stored on the model object (_mset_fuel_price_index_change)
    # rather than in the FTT input dict, so no change to FTT_Standalone's VariableListing.csv
    # is needed. model_class.py converts _mset_fuel_price_index_change to FPIX and injects it
    # into variables before calling ftt_p_solve each year.
    if year > 2019:
        # Assess price changes by FTT fuels.
        # DYNAMIC['delta_price_yoy'] are domestic price changes.
        # z_bp monetary flows weight the regional import price.
        fuel_pd = IO_model.IND_BASE.loc[IO_model.IND_BASE.index.get_level_values('TRAD_COMM').isin(ftt_model.ftt_fuel_converter.TRAD_COMM), 'z_bp'].copy()
        _dpy = self.V.read_var('delta_price_yoy', year, as_df=True).rename(columns={'delta_price_yoy': 'dp'})
        exp_fuel_pd = _dpy.loc[_dpy.PROD_COMM.isin(ftt_model.ftt_tech_converter.PROD_COMM)].copy()
        fuel_merged = pd.merge(fuel_pd.reset_index(), exp_fuel_pd, left_on='REG_exp', right_on='REG_imp', how='inner', suffixes=('', '_y'))

        # Year-on-year fractional change in fuel price per (region, T2TI technology); feeds FTT's cumulative FPIX.
        fuel_price_index_change = np.zeros((n_reg, n_tech, 1))

        for tech, sectors in ftt_model.ftt_tech_converter.groupby('T2TI'):
            sec_price_chng = fuel_merged.loc[fuel_merged.PROD_COMM.isin(sectors.PROD_COMM)]
            weighted_dp = (sec_price_chng.groupby("REG_imp", group_keys=False, dropna=False)
                            .apply(
                                lambda g: (g["dp"] * g["z_bp"]).sum() / g["z_bp"].sum()
                                if g["z_bp"].sum() != 0
                                else 0,
                                include_groups=False))
            tech_idx = ftt_model.titles['T2TI'].index(tech)
            weighted_dp = weighted_dp.reindex(_rti_short).fillna(0.0)
            fuel_price_index_change[:, tech_idx, 0] = weighted_dp.values

        ftt_model._mset_fuel_price_index_change = fuel_price_index_change
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
    ftt_model.variables, ftt_model.lags = ftt_model.solve_year(year, y, ftt_model.scenarios)
    # Populate output container
    for var in ftt_model.variables:
        if 'TIME' in ftt_model.dims[var]:
            ftt_model.output[ftt_model.scenarios][var][:, :, :, y] = ftt_model.variables[var]
        else:
            ftt_model.output[ftt_model.scenarios][var][:, :, :, 0] = ftt_model.variables[var]
    # Overwrite energy demand of the power sector after 2019
    # FTT power is used to estimate growth in energy demand
    # Therefore initial values from 2019 are needed
    if year > model_start:
        # Take energy demand from previous year
        ener_base_t0 = self.V.read_var_df('energy_flows', year - 1)
        # Filter on power sector
        power_ener_base = ener_base_t0.loc[ener_base_t0.PROD_COMM == '93'].copy()
        # Get primary energy demand values for t and t-1
        ftt_energy_dem_t = ftt_model.output[ftt_model.scenarios]['MEPD'][:, :, 0, y]
        ftt_energy_dem_t0 = ftt_model.output[ftt_model.scenarios]['MEPD'][:, :, 0, y - 1]
        # Read energy_flows once before the loop; all sector updates are applied in-place,
        # then written back once after the loop (avoids N reads+writes for N fuel sectors).
        _ef = self.V.read_var_df('energy_flows', year).set_index(['REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM'])
        _ftt_fuel_growth_by_sector = {}  # TRAD_COMM -> pd.Series(growth_ratio, index=RTI_short)
        # Loop over supplying sectors (skip TRAD_COMM=93: renewables/nuclear have no
        # fuel commodity input; including them corrupts the electricity demand fed back to FTT)
        for sector, fuels in ftt_model.ftt_fuel_converter.groupby('TRAD_COMM'):
            if sector == 93:
                continue
            # Get indices of corresponding fuels
            fuel_idx = [ftt_model.titles['ERTI'].index(f) for f in fuels.ERTI]
            # Get fuel demand for the given sectors
            fuel_demand_t = ftt_energy_dem_t[:, fuel_idx].sum(axis = 1)
            fuel_demand_t0 = ftt_energy_dem_t0[:, fuel_idx].sum(axis = 1)
            # Calculate growth
            ftt_energy_dem_growth =   np.divide(fuel_demand_t, fuel_demand_t0,
                                                out=np.ones_like(fuel_demand_t),
                                                where=fuel_demand_t0!=0)
            ftt_energy_dem_growth = pd.Series(ftt_energy_dem_growth, index = ftt_model.titles['RTI_short'])
            _ftt_fuel_growth_by_sector[sector] = ftt_energy_dem_growth
            # Filter energy data on sector
            power_ener_sec = power_ener_base.loc[power_ener_base.TRAD_COMM == sector].copy()
            power_ener_sec = power_ener_sec.rename(columns = {'fuel_use': 'fuel_use_new_adj'})

            power_ener_sec["growth"] = power_ener_sec["REG_imp"].map(ftt_energy_dem_growth)
            power_ener_sec["fuel_use_new_adj"] = power_ener_sec["fuel_use_new_adj"] * power_ener_sec["growth"]
            power_ener_sec = power_ener_sec.drop('growth', axis = 1)
            power_ener_sec['PROD_COMM'] = power_ener_sec['PROD_COMM'].astype(int)
            power_ener_sec['TRAD_COMM'] = power_ener_sec['TRAD_COMM'].astype(int)
            power_ener_sec = power_ener_sec.set_index(['REG_imp', 'REG_exp', 'PROD_COMM', 'TRAD_COMM'])
            # Accumulate updates into _ef (no write until all sectors are done)
            _ef.update(power_ener_sec)
        # Single write after all sector updates are applied
        self.V.write_var_df('energy_flows', year, _ef.reset_index())
        # Propagate FTT fuel-mix signal into new_IO for the power sector (PROD_COMM=93).
        # new_IO[year] was written by model_class.py (A_iochange × output) before FTT runs.
        # We overlay FTT's MEPD-based growth ratios on the genuine fuel input rows
        # (TRAD_COMM=93 is already excluded from _ftt_fuel_growth_by_sector by the continue above).
        # These updated z_bp / a_bp values become next year's IND_BASE via the
        # new_IO → IND_BASE roll-forward (initiate_modules.py:50).
        if _ftt_fuel_growth_by_sector:
            _new_io = self.V.read_var_df('new_IO', year)
            _power = _new_io['PROD_COMM'] == 93
            _pf = _power & _new_io['TRAD_COMM'].isin(_ftt_fuel_growth_by_sector)
            for _sector, _growth in _ftt_fuel_growth_by_sector.items():
                _m = _power & (_new_io['TRAD_COMM'] == _sector)
                if _m.any():
                    _new_io.loc[_m, 'z_bp'] *= (
                        _new_io.loc[_m, 'REG_imp'].astype(str).map(_growth).fillna(1.0)
                    )
            # Recompute a_bp for the rows we changed, then a_tech for all power rows.
            _new_io.loc[_pf, 'a_bp'] = np.where(
                _new_io.loc[_pf, 'output'] != 0,
                _new_io.loc[_pf, 'z_bp'] / _new_io.loc[_pf, 'output'],
                0.0
            )
            _new_io.loc[_power, 'a_tech'] = (
                _new_io[_power]
                .groupby(['REG_imp', 'TRAD_COMM', 'PROD_COMM'])['a_bp']
                .transform('sum')
            )
            self.V.write_var_df('new_IO', year, _new_io)
    # Assess investment
    ftt_model.investment[year] = ftt_investment_by_mrio_sector(ftt_model, y)
    # Convert mEUR 2010 to mUSD 2010 and then to mUSD 2019
    ftt_model.investment[year] = ftt_model.investment[year] * 1.33 * 1.17

    # Export results in the last year
    if year == model_end:
        # Update scenario log
        scenarios_log = {}
        scenarios_log['S0'] = {}
        scenarios_log['S0']['run'] = datetime.datetime.timestamp(datetime.datetime.now())
        scenarios_log['S0']['description'] = "Test Scenario, provided by Cambridge Econometrics"
        scenarios_log['S0']['years'] = [str(x) for x in ftt_model.timeline]
        # Save metadata on current model run
        output_dir = Path('.') / 'MINDSET_FTT_Power' / 'Output'
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / 'Scenarios.json', 'w') as f:
            json.dump(scenarios_log, f)

        with open(output_dir / 'Results.pickle', 'wb') as f:
            pickle.dump(ftt_model.output, f)
            
    return ftt_model, DYNAMIC