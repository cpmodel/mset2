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
    # FPI is stored on the model object (_mset_fpi) rather than in the FTT input dict,
    # so no change to FTT_Standalone's VariableListing.csv is needed.
    # model_class.py converts _mset_fpi to FPIX and injects it into variables before
    # calling ftt_p_solve each year.
    if year > 2019:
        # Assess price changes by FTT fuels.
        # DYNAMIC['delta_price_yoy'] are domestic price changes.
        # z_bp monetary flows weight the regional import price.
        fuel_pd = IO_model.IND_BASE.loc[IO_model.IND_BASE.index.get_level_values('TRAD_COMM').isin(ftt_model.ftt_fuel_converter.TRAD_COMM), 'z_bp'].copy()
        _dpy = self.V.read_var('delta_price_yoy', year, as_df=True).rename(columns={'delta_price_yoy': 'dp'})
        exp_fuel_pd = _dpy.loc[_dpy.PROD_COMM.isin(ftt_model.ftt_tech_converter.PROD_COMM)].copy()
        fuel_merged = pd.merge(fuel_pd.reset_index(), exp_fuel_pd, left_on='REG_exp', right_on='REG_imp', how='inner', suffixes=('', '_y'))

        fpi = np.zeros((n_reg, n_tech, 1))

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
            fpi[:, tech_idx, 0] = weighted_dp.values

        ftt_model._mset_fpi = fpi
    # Carbon price: per-(region, technology) ctax in EUR2015/tCO2.
    # model_class.solve_year() applies the EUR2015→USD2013 conversion using current-year FTT exchange-rate variables.
    c_price_power = Scenario.tax_rate.loc[Scenario.tax_rate.PROD_COMM == 93].copy()
    reppx_arr = np.zeros((n_reg, n_tech, 1))
    # converters.csv uses numbered T2TI names matching titles['T2TI'] (converters.xlsx/ftt_t2ti_erti.csv use short names — wrong for this lookup)
    _conv_csv = pd.read_csv(Path('MINDSET_FTT_Power/Utilities/titles/converters.csv'))
    _t2ti_list = list(ftt_model.titles['T2TI'])
    _erti_to_t2ti_idxs = {}
    for _, row in _conv_csv.iterrows():
        _erti_to_t2ti_idxs.setdefault(row['ERTI'], []).append(_t2ti_list.index(row['T2TI']))
    for fuel, sectors in ftt_model.ftt_fuel_converter.groupby('ERTI'):
        if fuel not in _erti_to_t2ti_idxs:
            continue
        sec_c_price = c_price_power.loc[c_price_power.TRAD_COMM.isin(sectors.TRAD_COMM)]
        if len(sec_c_price) == 0:
            continue
        avg_by_reg = sec_c_price.groupby('REG_imp')['ctax'].mean()
        for tech_idx in _erti_to_t2ti_idxs[fuel]:
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
        # Loop over supplying sectors
        for sector, fuels in ftt_model.ftt_fuel_converter.groupby('TRAD_COMM'):
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
    # Assess investment
    # Reorder MWIY columns to match ftt_inv_converter, then map to MRIO sectors.
    _mwiy_raw = ftt_model.output[ftt_model.scenarios]['MWIY'][:, :, 0, y]
    _mwiy12 = pd.DataFrame(_mwiy_raw, columns=list(ftt_model.titles['T2TI'])) \
                .reindex(columns=list(ftt_model.ftt_inv_converter.columns)).values
    ftt_model.investment[year] = (
        np.array(ftt_model.ftt_inv_converter)[np.newaxis, :, :] *
        _mwiy12[:, np.newaxis, :]
    ).sum(axis=2)
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
        with open(Path('.') / 'MINDSET_FTT_Power' / 'Output' / 'Scenarios.json', 'w') as f:
            json.dump(scenarios_log, f)

        with open(Path('.') / 'MINDSET_FTT_Power' / 'Output' / 'Results.pickle', 'wb') as f:
            pickle.dump(ftt_model.output, f)
            
    return ftt_model, DYNAMIC