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
"""

import numpy as np
from pathlib import Path

from MINDSET_FTT_Power.SourceCode.support.ftt_region_map import RegionMap


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
    _solve_and_store(tr, year, year - tr.ftt_start)
