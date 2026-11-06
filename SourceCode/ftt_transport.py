# -*- coding: utf-8 -*-
"""
FTT:Transport as a second FTT run next to MSET.

FTT-Tr runs through the MINDSET_FTT_Power wrapper as its own run at its native regions (71),
MSET at IPCC-10. Region conversion between the two goes through one RegionMap
(MINDSET_FTT_Power/SourceCode/support/ftt_region_map.py); with ftt_tr_region_mode = identity
the same code runs with MSET and FTT at equal resolution.

Hooks, wired in SourceCode/model_class.py (all behind ftt_tr_run = True):
    setup_ftt_transport(mset)             once, at model construction
    solve_year_ftt_transport(mset, ...)   every MSET year, after the FTT:Power step
    apply_household_consumption(mset, ...) every MSET year, on household_consumption just before it is written

MSET -> FTT-Tr (before solving):
    CO2taxTr   household carbon price on the transport fuels, broadcast to FTT regions
    PFRM/PFRE  cumulative household fuel-price index (year-on-year, like FPIX for Power),
               broadcast to FTT regions, applied to FTT-Tr's own E3ME fuel prices
FTT-Tr -> MSET (after solving):
    TJEF       collapsed live (sum over FTT regions per MSET region); its year-on-year growth
               replaces MSET's own growth for the transport share of household consumption of
               fuels (household_consumption, and energy_flows_fd to stay consistent)
"""

import numpy as np
import pandas as pd
from pathlib import Path

from MINDSET_FTT_Power.SourceCode.support.ftt_region_map import RegionMap

KTOE_TO_TJ = 41.868
UTIL = Path('MINDSET_FTT_Power') / 'Utilities'


# ------------------------------------------------------------------ setup
def setup_ftt_transport(mset):
    """Build the FTT-Tr run, its region map and converters, and solve the years before MSET starts."""
    from MINDSET_FTT_Power.SourceCode.model_class import ModelRun as FTTRun

    tr = FTTRun(settings_path=mset.ftt_tr_settings)
    tr.ftt_start = min(tr.timeline)

    ftt_codes = list(tr.titles['RTI_short'])
    mset_codes = list(mset.EXOG_VARS.R_list)
    if mset.ftt_tr_region_mode == 'identity':
        tr.region_map = RegionMap.identity(ftt_codes, mset_codes)
    else:
        tr.region_map = RegionMap.from_crosswalk(mset.ftt_tr_crosswalk, ftt_codes, mset_codes)

    fuels = pd.read_csv(UTIL / 'ftt_tr_to_mindset_fuels.csv').dropna(subset=['TRAD_COMM'])
    fuels['TRAD_COMM'] = fuels['TRAD_COMM'].astype(int)
    tr.fuel_map = fuels                                    # JTI -> MSET commodity
    tr.carbon_fuel_comm = [c for c in fuels['TRAD_COMM'] if c != 93]   # carbon price = household rate on liquid fuels

    prices = pd.read_csv(UTIL / 'ftt_tr_fuel_price_mapping.csv').dropna(subset=['TRAD_COMM'])
    prices['TRAD_COMM'] = prices['TRAD_COMM'].astype(int)
    tr.price_map = prices                                  # PFRx -> MSET commodity
    tr.price_index = {v: np.ones(len(ftt_codes)) for v in prices['PFR_var']}
    tr.signals = {}
    tr.couple_household_energy = mset.ftt_tr_couple_household_energy

    for y, year in enumerate(np.arange(tr.ftt_start, min(mset.years))):
        _solve_and_store(tr, year, y)

    _report_coverage(tr, year=min(mset.years))
    mset.ftt_tr_model = tr


def _solve_and_store(tr, year, y):
    tr.variables, tr.lags = tr.solve_year(year, y, tr.scenarios)
    out = tr.output[tr.scenarios]
    for var, val in tr.variables.items():
        if 'TIME' in tr.dims[var]:
            out[var][:, :, :, y] = val
        else:
            out[var][:, :, :, 0] = val


def _active_regions(tr, year):
    """FTT regions FTT-Tr actually simulates in `year`: it skips regions without fleet data."""
    inp = tr.input[tr.scenarios]
    y = year - tr.ftt_start
    return (inp['RFLT'][:, 0, 0, y] > 0) & (inp['TDA1'][:, 0, 0, 0] < year)


def _report_coverage(tr, year):
    rm = tr.region_map
    have_data = tr.input[tr.scenarios]['RFLT'][:, 0, 0, year - tr.ftt_start] > 0
    n = rm.collapse_sum(np.ones(len(rm.ftt_codes)))
    n_data = rm.collapse_sum(have_data.astype(float))
    lost = [c for c, d in zip(rm.ftt_codes, have_data) if not d]
    print(f"FTT-Tr: {int(have_data.sum())}/{len(have_data)} FTT regions have fleet data in {year}; "
          f"no fleet data (not calculated): {lost}")
    print("FTT-Tr coverage (share of mapped FTT regions with fleet data): " +
          ", ".join(f"{c} {d / t:.0%}" for c, d, t in zip(rm.mset_codes, n_data, n)))


# ------------------------------------------------------------- per-year hook
def solve_year_ftt_transport(mset, year, DYNAMIC, Scenario):
    tr = mset.ftt_tr_model
    y = year - tr.ftt_start
    tr._mset_tr = _mset_to_ftt(mset, tr, year, DYNAMIC, Scenario)
    _solve_and_store(tr, year, y)
    tr.signals[year] = _collapse_outputs(tr, year, y)


# ------------------------------------------------------------- MSET -> FTT
def _mset_to_ftt(mset, tr, year, DYNAMIC, Scenario):
    rm = tr.region_map
    sig = {'CO2taxTr': None, 'fuel_price_index': {}}

    # Carbon price: household (FD_1) tax rate on the transport fuel commodities, USD/tCO2.
    tax = Scenario.tax_rate
    hh = tax.loc[(tax['PROD_COMM'].astype(str) == 'FD_1')
                 & (pd.to_numeric(tax['TRAD_COMM'], errors='coerce').isin(tr.carbon_fuel_comm))]
    if len(hh) and (hh['ctax'] != 0).any():
        by_region = hh.groupby('REG_imp')['ctax'].mean()
        sig['CO2taxTr'] = rm.broadcast(by_region) * tr.carbon_price_conv_factor

    # Fuel-price index: cumulative product of MSET's year-on-year commodity price change, kept
    # per FTT region and applied to FTT-Tr's own E3ME fuel prices (as FPIX is for Power).
    if year > mset.model_start:
        dp_all = mset.V.read_var('delta_price_yoy', year, as_df=True).rename(
            columns={'delta_price_yoy': 'dp'})
        hh_cons = mset.V.read_var('household_consumption', year - 1, as_df=True)
        for _, row in tr.price_map.iterrows():
            var, comm = row['PFR_var'], int(row['TRAD_COMM'])
            sig['fuel_price_index'][var] = tr.price_index[var].copy()
            dp = _household_price_change(dp_all, hh_cons, comm)
            tr.price_index[var] = tr.price_index[var] * (1.0 + rm.broadcast(dp))
    return sig


def _household_price_change(dp_all, hh_cons, comm):
    """Year-on-year price change of commodity `comm` faced by households of each MSET region,
    weighting the supplying regions by last year's household purchases."""
    dp = dp_all.loc[pd.to_numeric(dp_all['PROD_COMM'], errors='coerce') == comm, ['REG_imp', 'dp']].rename(
        columns={'REG_imp': 'REG_exp'})
    w = hh_cons.loc[pd.to_numeric(hh_cons['TRAD_COMM'], errors='coerce') == comm,
                    ['REG_imp', 'REG_exp', 'household_consumption']]
    w = w.merge(dp, on='REG_exp', how='left').fillna({'dp': 0.0})
    w['num'] = w['household_consumption'] * w['dp']
    g = w.groupby('REG_imp')[['num', 'household_consumption']].sum()
    return (g['num'] / g['household_consumption'].where(g['household_consumption'] != 0)).fillna(0.0)


# ------------------------------------------------------------- FTT -> MSET
def _collapse_outputs(tr, year, y):
    """Collapse FTT-Tr's FTT-region outputs to MSET regions. All are additive, so a plain sum."""
    rm = tr.region_map
    out = tr.output[tr.scenarios]
    jti = list(tr.titles['JTI'])
    tjef, tjef_prev = out['TJEF'][:, :, 0, y], out['TJEF'][:, :, 0, y - 1]

    # Until a region's TDA1 FTT-Tr replays historical data; only regions it simulates in `year`
    # carry a model signal, so growth and the FTT share of household use use those alone.
    active = _active_regions(tr, year).astype(float)
    fuel = {}
    for comm, grp in tr.fuel_map.groupby('TRAD_COMM'):
        idx = [jti.index(j) for j in grp['JTI']]
        now, prev = tjef[:, idx].sum(axis=1), tjef_prev[:, idx].sum(axis=1)
        fuel[comm] = pd.DataFrame({
            'ftt_use_tj': rm.collapse_sum(now) * KTOE_TO_TJ,
            'sim_use_prev_tj': rm.collapse_sum(prev * active) * KTOE_TO_TJ,
            'growth': rm.growth(now * active, prev * active),
        }, index=rm.mset_codes)
    return {'fuel': fuel}                                                    # by commodity


def apply_household_consumption(mset, year, hh_cons):
    return _adjust_household_consumption(mset, year, hh_cons)


def _adjust_household_consumption(mset, year, hh_cons):
    """Household consumption of fuels follows FTT-Tr for the transport part.

    hh_cons: DataFrame indexed (REG_imp, REG_exp, TRAD_COMM) with column VIPA (this year's
    household consumption as computed by MSET). With rho the share of last year's household
    fuel use (physical, energy_flows_fd) that FTT-Tr models, G the growth of its collapsed
    fuel use and d MSET's own growth of that consumption, the coupled growth is
    (1 - rho) * d + rho * (G - 1); each row is rescaled by (1 + coupled) / (1 + d).
    energy_flows_fd is rescaled by the same factor to stay consistent.
    """
    tr = mset.ftt_tr_model
    sig = tr.signals.get(year) if tr is not None else None
    if sig is None or not tr.couple_household_energy or year <= mset.model_start:
        return hh_cons

    prev_c = mset.V.read_var('household_consumption', year - 1, as_df=True)
    prev_c['TRAD_COMM'] = pd.to_numeric(prev_c['TRAD_COMM'], errors='coerce')
    ef_prev = mset.V.read_var_df('energy_flows_fd', year - 1)
    ef_prev = ef_prev[ef_prev['FD'].astype(str) == 'FD_1'].copy()
    ef_prev['TRAD_COMM'] = pd.to_numeric(ef_prev['TRAD_COMM'], errors='coerce')

    reg = hh_cons.index.get_level_values('REG_imp')
    comm = pd.to_numeric(pd.Series(hh_cons.index.get_level_values('TRAD_COMM')), errors='coerce').to_numpy()
    factor = np.ones(len(hh_cons))
    region_factors = {}
    for c, f in sig['fuel'].items():
        c_prev = prev_c.loc[prev_c['TRAD_COMM'] == c].groupby('REG_imp')['household_consumption'].sum().reindex(f.index)
        c_now = hh_cons['VIPA'][comm == c].groupby(level='REG_imp').sum().reindex(f.index)
        e_prev = ef_prev.loc[ef_prev['TRAD_COMM'] == c].groupby('REG_imp')['fuel_use'].sum().reindex(f.index)
        d = (c_now / c_prev.where(c_prev > 0) - 1.0).fillna(0.0)
        rho = (f['sim_use_prev_tj'] / e_prev.where(e_prev > 0)).fillna(0.0)
        if (rho > 1).any():
            print(f"FTT-Tr: FTT-Tr fuel use exceeds household fuel use for commodity {c} in "
                  f"{list(rho.index[rho > 1])}; rho capped at 1 (check units / coverage)")
        rho = rho.clip(0.0, 1.0)
        f['rho'] = rho
        region_factors[c] = ((1.0 + (1.0 - rho) * d + rho * (f['growth'] - 1.0)) / (1.0 + d)).to_dict()
        rows = comm == c
        factor[rows] = pd.Series(reg[rows]).map(region_factors[c]).fillna(1.0).to_numpy()

    out = hh_cons.copy()
    out['VIPA'] = out['VIPA'] * factor

    ef = mset.V.read_var_df('energy_flows_fd', year)
    is_hh = (ef['FD'].astype(str) == 'FD_1').to_numpy()
    ef_comm = pd.to_numeric(ef['TRAD_COMM'], errors='coerce').to_numpy()
    ef_factor = np.ones(len(ef))
    for c, rf in region_factors.items():
        rows = is_hh & (ef_comm == c)
        ef_factor[rows] = ef.loc[rows, 'REG_imp'].map(rf).fillna(1.0).to_numpy()
    ef['fuel_use'] = ef['fuel_use'] * ef_factor
    mset.V.write_var_df('energy_flows_fd', year, ef)
    return out
