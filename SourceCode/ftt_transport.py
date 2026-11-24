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
    export_ftt_transport_results(ftt_model) after household adjustment in the final year

MSET -> FTT-Tr (before solving):
    CO2taxTr   household carbon price on the transport fuels, broadcast to FTT regions
    PFRM/PFRE  cumulative household fuel-price index (year-on-year, like FPIX for Power),
               broadcast to FTT regions, applied to FTT-Tr's own E3ME fuel prices
FTT-Tr -> MSET (after solving):
    TJEF       collapsed live (sum over FTT regions per MSET region); its year-on-year growth
               replaces MSET's own growth for the transport share of household consumption of
               fuels (household_consumption, and energy_flows_fd to stay consistent)
    TWIY, TEWE, TEWK   collapsed and recorded per year (output csv only, not fed into MSET)
"""

import numpy as np
import pandas as pd
from pathlib import Path

from MINDSET_FTT_Power.SourceCode.support.ftt_region_map import RegionMap
from SourceCode.ftt_common import export_ftt_results, solve_and_store

KTOE_TO_TJ = 41.868
UTILITIES_DIR = Path('MINDSET_FTT_Power') / 'Utilities'


def setup_ftt_transport(mset):
    """Build the FTT-Transport run and solve the years before MSET starts.

    Sets up the region map, fuel mappings and price indices needed for
    coupling. The run is stored in ``mset.ftt_tr_model`` after its pre-MSET
    years have been solved.

    Args:
        mset: MSET model providing settings, regions and the simulation years.

    Returns:
        None: The FTT-Transport run is stored on the MSET model.
    """
    from MINDSET_FTT_Power.SourceCode.model_class import ModelRun as FTTRun

    ftt_model = FTTRun(model_end=mset.model_end, settings_path=mset.ftt_tr_settings)
    ftt_model.ftt_start = min(ftt_model.timeline)

    ftt_region_codes = list(ftt_model.titles['RTI_short'])
    mset_region_codes = list(mset.EXOG_VARS.R_list)
    if mset.ftt_tr_region_mode == 'identity':
        ftt_model.region_map = RegionMap.identity(ftt_region_codes, mset_region_codes)
    else:
        ftt_model.region_map = RegionMap.from_crosswalk(
            mset.ftt_tr_crosswalk, ftt_region_codes, mset_region_codes
        )

    # Gas, biofuels and hydrogen are currently unmapped to MSET commodities.
    fuel_mapping = pd.read_csv(UTILITIES_DIR / 'ftt_tr_to_mindset_fuels.csv').dropna(subset=['TRAD_COMM'])
    fuel_mapping['TRAD_COMM'] = fuel_mapping['TRAD_COMM'].astype(int)
    ftt_model.fuel_map = fuel_mapping
    ftt_model.carbon_fuel_comm = [commodity for commodity in fuel_mapping['TRAD_COMM'] if commodity != 93]

    price_mapping = pd.read_csv(UTILITIES_DIR / 'ftt_tr_fuel_price_mapping.csv').dropna(subset=['TRAD_COMM'])
    price_mapping['TRAD_COMM'] = price_mapping['TRAD_COMM'].astype(int)
    ftt_model.price_map = price_mapping
    ftt_model.price_index = {variable: np.ones(len(ftt_region_codes)) for variable in price_mapping['PFR_var']}
    ftt_model.signals = {}
    ftt_model.couple_household_energy = mset.ftt_tr_couple_household_energy

    setup_years = np.arange(ftt_model.ftt_start, min(mset.years))
    for ftt_yr_idx, year in enumerate(setup_years):
        solve_and_store(ftt_model, year, ftt_yr_idx)

    _report_coverage(ftt_model, year=min(mset.years))
    mset.ftt_tr_model = ftt_model


def _active_regions(ftt_model, year):
    """Identify FTT regions with fleet data that are simulated in the given year."""
    scenario_inputs = ftt_model.input[ftt_model.scenarios]
    ftt_yr_idx = year - ftt_model.ftt_start
    return (scenario_inputs['RFLT'][:, 0, 0, ftt_yr_idx] > 0) & (scenario_inputs['TDA1'][:, 0, 0, 0] < year)


def _report_coverage(ftt_model, year):
    """Print the share of mapped FTT regions with fleet data for each MSET region."""
    region_map = ftt_model.region_map
    has_fleet_data = ftt_model.input[ftt_model.scenarios]['RFLT'][:, 0, 0, year - ftt_model.ftt_start] > 0
    mapped_regions = region_map.collapse_sum(np.ones(len(region_map.ftt_codes)))
    mapped_regions_with_data = region_map.collapse_sum(has_fleet_data.astype(float))
    regions_without_data = [code for code, has_data in zip(region_map.ftt_codes, has_fleet_data) if not has_data]
    print(f"FTT-Tr: {int(has_fleet_data.sum())}/{len(has_fleet_data)} FTT regions have fleet data in {year}; "
          f"no fleet data (not calculated): {regions_without_data}")
    print("FTT-Tr coverage (share of mapped FTT regions with fleet data): " +
          ", ".join(f"{code} {with_data / total:.0%}" for code, with_data, total
                    in zip(region_map.mset_codes, mapped_regions_with_data, mapped_regions)))


def solve_year_ftt_transport(mset, year, Scenario):
    """Run one year of FTT-Transport and prepare its results for MSET.

    Maps MSET carbon prices and fuel-price changes to FTT regions, solves the
    year, and stores outputs aggregated to MSET regions. Household consumption
    is adjusted separately after MSET calculates it.

    Args:
        mset: MSET model containing the FTT-Transport run and variable table.
        year (int): Current simulation year.
        Scenario: Scenario providing household carbon prices in ``tax_rate``.

    Returns:
        None: The FTT-Transport run is updated in place on the MSET model.
    """
    ftt_model = mset.ftt_tr_model
    ftt_yr_idx = year - ftt_model.ftt_start
    ftt_model._mset_tr = _mset_to_ftt(mset, ftt_model, year, Scenario)
    solve_and_store(ftt_model, year, ftt_yr_idx)
    ftt_model.signals[year] = _collapse_outputs(ftt_model, year, ftt_yr_idx)


def _mset_to_ftt(mset, ftt_model, year, Scenario):
    """Map MSET household carbon prices and fuel-price indices to FTT regions.

    Args:
        mset: MSET model providing prices and household consumption.
        ftt_model: FTT-Transport run providing mappings and price indices.
        year (int): Current simulation year.
        Scenario: Scenario providing household carbon prices in ``tax_rate``.

    Returns:
        dict: Carbon-price and fuel-price-index signals for the FTT solver.
    """
    region_map = ftt_model.region_map
    signals = {'CO2taxTr': None, 'fuel_price_index': {}}

    # Carbon price: household (FD_1) tax rate on the transport fuel commodities, USD/tCO2.
    tax_rates = Scenario.tax_rate
    household_tax_rates = tax_rates.loc[(tax_rates['PROD_COMM'].astype(str) == 'FD_1')
                                       & (pd.to_numeric(tax_rates['TRAD_COMM'], errors='coerce')
                                          .isin(ftt_model.carbon_fuel_comm))]
    if len(household_tax_rates) and (household_tax_rates['ctax'] != 0).any():
        carbon_price_by_region = household_tax_rates.groupby('REG_imp')['ctax'].mean()
        signals['CO2taxTr'] = region_map.broadcast(carbon_price_by_region) * ftt_model.carbon_price_conv_factor

    # Fuel-price index: cumulative product of MSET's year-on-year commodity price change, kept
    # per FTT region and applied to FTT-Tr's own E3ME fuel prices (as FPIX is for Power).
    if year > mset.model_start:
        price_changes = mset.V.read_var('delta_price_yoy', year, as_df=True).rename(
            columns={'delta_price_yoy': 'dp'})
        household_consumption = mset.V.read_var('household_consumption', year - 1, as_df=True)
        for _, row in ftt_model.price_map.iterrows():
            price_variable, commodity = row['PFR_var'], int(row['TRAD_COMM'])
            signals['fuel_price_index'][price_variable] = ftt_model.price_index[price_variable].copy()
            price_change = _household_price_change(price_changes, household_consumption, commodity)
            ftt_model.price_index[price_variable] = (
                ftt_model.price_index[price_variable] * (1.0 + region_map.broadcast(price_change))
            )
    return signals


def _household_price_change(price_changes, household_consumption, commodity):
    """Calculate each region's household price change for a commodity.

    Exporter price changes are weighted by the previous year's household
    purchases from each exporter.

    Args:
        price_changes (pd.DataFrame): Current year price changes by producer.
        household_consumption (pd.DataFrame): Previous year purchases by region.
        commodity (int): MSET commodity code.

    Returns:
        pd.Series: Weighted price change indexed by importing region.
    """
    exporter_price_changes = price_changes.loc[
        pd.to_numeric(price_changes['PROD_COMM'], errors='coerce') == commodity, ['REG_imp', 'dp']
    ].rename(
        columns={'REG_imp': 'REG_exp'})
    purchases = household_consumption.loc[
        pd.to_numeric(household_consumption['TRAD_COMM'], errors='coerce') == commodity,
        ['REG_imp', 'REG_exp', 'household_consumption']
    ]
    purchases = purchases.merge(exporter_price_changes, on='REG_exp', how='left').fillna({'dp': 0.0})
    purchases['num'] = purchases['household_consumption'] * purchases['dp']
    regional_totals = purchases.groupby('REG_imp')[['num', 'household_consumption']].sum()
    return (regional_totals['num'] / regional_totals['household_consumption'].where(
        regional_totals['household_consumption'] != 0)).fillna(0.0)


def _collapse_outputs(ftt_model, year, ftt_yr_idx):
    """Aggregate FTT-Transport outputs to MSET regions.

    Fuel-use growth uses only FTT regions actively simulated in the current
    year; the other reported outputs are aggregated across all mapped regions.

    Args:
        ftt_model: FTT-Transport run with stored outputs and region mappings.
        year (int): Current simulation year.
        ftt_yr_idx (int): Current year index in FTT's time dimension.

    Returns:
        dict: Fuel-use signals and other FTT outputs indexed by MSET region.
    """
    region_map = ftt_model.region_map
    output = ftt_model.output[ftt_model.scenarios]
    fuel_types = list(ftt_model.titles['JTI'])
    current_fuel_use = output['TJEF'][:, :, 0, ftt_yr_idx]
    previous_fuel_use = output['TJEF'][:, :, 0, ftt_yr_idx - 1]

    # Until a region's TDA1 FTT-Tr replays historical data; only regions it simulates in `year`
    # carry a model signal, so growth and the FTT share of household use use those alone.
    active_regions = _active_regions(ftt_model, year).astype(float)
    fuel_signals = {}
    for commodity, mapped_fuels in ftt_model.fuel_map.groupby('TRAD_COMM'):
        fuel_indices = [fuel_types.index(fuel) for fuel in mapped_fuels['JTI']]
        current_commodity_use = current_fuel_use[:, fuel_indices].sum(axis=1)
        previous_commodity_use = previous_fuel_use[:, fuel_indices].sum(axis=1)
        fuel_signals[commodity] = pd.DataFrame({
            'ftt_use_tj': region_map.collapse_sum(current_commodity_use) * KTOE_TO_TJ,
            'sim_use_prev_tj': region_map.collapse_sum(previous_commodity_use * active_regions) * KTOE_TO_TJ,
            'growth': region_map.growth(
                current_commodity_use * active_regions, previous_commodity_use * active_regions),
        }, index=region_map.mset_codes)
    mapped_regions = region_map.collapse_sum(np.ones(len(region_map.ftt_codes)))
    return {
        'fuel': fuel_signals,
        'TJEF_ktoe': pd.DataFrame(
            region_map.collapse_sum(current_fuel_use), index=region_map.mset_codes, columns=fuel_types),
        'TWIY': pd.Series(
            region_map.collapse_sum(output['TWIY'][:, :, 0, ftt_yr_idx].sum(axis=1)), index=region_map.mset_codes),
        'TEWE_Mt': pd.Series(
            region_map.collapse_sum(output['TEWE'][:, :, 0, ftt_yr_idx].sum(axis=1)), index=region_map.mset_codes),
        'TEWK_kveh': pd.Series(
            region_map.collapse_sum(output['TEWK'][:, :, 0, ftt_yr_idx].sum(axis=1)), index=region_map.mset_codes),
        'active_share': pd.Series(
            region_map.collapse_sum(active_regions) / mapped_regions, index=region_map.mset_codes),
    }


def apply_household_consumption(mset, year, hh_cons):
    """Adjust household fuel consumption using FTT-Transport fuel-use growth.

    The growth rate combines FTT growth for the transport share of fuel use
    with MSET's own growth for the remaining share. Household energy flows are
    rescaled by the same factor to stay consistent.

    If ``rho`` is the transport share, ``d`` is MSET's growth rate and ``G``
    is FTT's growth factor, the combined growth rate is
    ``(1 - rho) * d + rho * (G - 1)``.

    Args:
        mset: MSET model providing the FTT run and household energy flows.
        year (int): Current simulation year.
        hh_cons (pd.DataFrame): MSET consumption with a ``VIPA`` column,
            indexed by ``REG_imp``, ``REG_exp`` and ``TRAD_COMM``.

    Returns:
        pd.DataFrame: Adjusted household consumption, or the original input
        when no signal is available, coupling is disabled or it is the first
        MSET year.
    """
    ftt_model = mset.ftt_tr_model
    signals = ftt_model.signals.get(year) if ftt_model is not None else None
    if signals is None or not ftt_model.couple_household_energy or year <= mset.model_start:
        return hh_cons

    previous_consumption = mset.V.read_var('household_consumption', year - 1, as_df=True)
    previous_consumption['TRAD_COMM'] = pd.to_numeric(previous_consumption['TRAD_COMM'], errors='coerce')
    previous_energy_flows = mset.V.read_var_df('energy_flows_fd', year - 1)
    previous_energy_flows = previous_energy_flows[previous_energy_flows['FD'].astype(str) == 'FD_1'].copy()
    previous_energy_flows['TRAD_COMM'] = pd.to_numeric(previous_energy_flows['TRAD_COMM'], errors='coerce')

    importing_regions = hh_cons.index.get_level_values('REG_imp')
    commodities = pd.to_numeric(pd.Series(hh_cons.index.get_level_values('TRAD_COMM')), errors='coerce').to_numpy()
    consumption_factors = np.ones(len(hh_cons))
    region_factors = {}
    for commodity, fuel_signal in signals['fuel'].items():
        consumption_prev = previous_consumption.loc[
            previous_consumption['TRAD_COMM'] == commodity
        ].groupby('REG_imp')['household_consumption'].sum().reindex(fuel_signal.index)
        consumption_now = hh_cons['VIPA'][commodities == commodity].groupby(
            level='REG_imp').sum().reindex(fuel_signal.index)
        energy_prev = previous_energy_flows.loc[
            previous_energy_flows['TRAD_COMM'] == commodity
        ].groupby('REG_imp')['fuel_use'].sum().reindex(fuel_signal.index)
        mset_growth = (consumption_now / consumption_prev.where(consumption_prev > 0) - 1.0).fillna(0.0)
        rho = (fuel_signal['sim_use_prev_tj'] / energy_prev.where(energy_prev > 0)).fillna(0.0)
        if (rho > 1).any():
            print(f"FTT-Tr: FTT-Tr fuel use exceeds household fuel use for commodity {commodity} in "
                  f"{list(rho.index[rho > 1])}; rho capped at 1 (check units / coverage)")
        rho = rho.clip(0.0, 1.0)
        fuel_signal['rho'] = rho
        region_factors[commodity] = (
            (1.0 + (1.0 - rho) * mset_growth + rho * (fuel_signal['growth'] - 1.0))
            / (1.0 + mset_growth)
        ).to_dict()
        commodity_rows = commodities == commodity
        consumption_factors[commodity_rows] = pd.Series(importing_regions[commodity_rows]).map(
            region_factors[commodity]).fillna(1.0).to_numpy()

    adjusted_consumption = hh_cons.copy()
    adjusted_consumption['VIPA'] = adjusted_consumption['VIPA'] * consumption_factors

    energy_flows = mset.V.read_var_df('energy_flows_fd', year)
    household_rows = (energy_flows['FD'].astype(str) == 'FD_1').to_numpy()
    energy_commodities = pd.to_numeric(energy_flows['TRAD_COMM'], errors='coerce').to_numpy()
    energy_factors = np.ones(len(energy_flows))
    for commodity, factors_by_region in region_factors.items():
        commodity_rows = household_rows & (energy_commodities == commodity)
        energy_factors[commodity_rows] = energy_flows.loc[commodity_rows, 'REG_imp'].map(
            factors_by_region).fillna(1.0).to_numpy()
    energy_flows['fuel_use'] = energy_flows['fuel_use'] * energy_factors
    mset.V.write_var_df('energy_flows_fd', year, energy_flows)
    return adjusted_consumption


def export_ftt_transport_results(ftt_model):
    """Export aggregated and full FTT-Transport results.

    Args:
        ftt_model: FTT-Transport run containing yearly signals and outputs.
    """
    _write_collapsed(ftt_model)
    _write_results(ftt_model)


def _write_collapsed(ftt_model):
    """Write FTT-Transport signals aggregated to MSET regions as a CSV."""
    rows = []
    for year, signals in ftt_model.signals.items():
        for region in ftt_model.region_map.mset_codes:
            rows.append({'year': year, 'REG': region, 'variable': 'TWIY', 'item': '',
                         'value': signals['TWIY'][region]})
            rows.append({'year': year, 'REG': region, 'variable': 'TEWE_Mt', 'item': '',
                         'value': signals['TEWE_Mt'][region]})
            rows.append({'year': year, 'REG': region, 'variable': 'TEWK_kveh', 'item': '',
                         'value': signals['TEWK_kveh'][region]})
            rows.append({'year': year, 'REG': region, 'variable': 'active_share', 'item': '',
                         'value': signals['active_share'][region]})
            for fuel_type, value in signals['TJEF_ktoe'].loc[region].items():
                rows.append({'year': year, 'REG': region, 'variable': 'TJEF_ktoe',
                             'item': fuel_type, 'value': value})
            for commodity, fuel_signal in signals['fuel'].items():
                for column in fuel_signal.columns:
                    rows.append({'year': year, 'REG': region, 'variable': f'fuel_{column}', 'item': commodity,
                                 'value': fuel_signal.loc[region, column]})
    output_dir = Path('MINDSET_FTT_Power') / 'Output'
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_dir / 'ftt_tr_collapsed.csv', index=False)


def _write_results(ftt_model):
    """Write full FTT-Transport results in a separate folder from FTT-Power."""
    export_ftt_results(ftt_model, Path('MINDSET_FTT_Power') / 'Output' / 'FTT_Tr')
