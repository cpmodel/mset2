# -*- coding: utf-8 -*-
"""
Created on Fri Dec  5 09:44:43 2025

@author: hartvig
"""
import pandas as pd
import numpy as np
import time
import gc
import dill


from SourceCode.scenario import scenario
from SourceCode.InputOutput import IO
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df, MRIO_mat_to_df
from SourceCode.ener_elas import ener_elas 
from SourceCode.ener_balance import ener_balance
from SourceCode.BTA import BTA
from SourceCode.price import price
from SourceCode.tax_rev import tax_rev as tax_rev_mod
from SourceCode.prod_cost import prod_cost
from SourceCode.income import income
from SourceCode.household import household as hh
from SourceCode.government import gov
from SourceCode.trade import trade
from SourceCode.investment import invest
from SourceCode.employment import empl
from SourceCode.cost_curves import cost_curves

def initiate_modules(self, DYNAMIC, EXOG_VARS, MRIO_df_to_vec_DEF, MRIO_vec_to_df_DEF, CALIBRATING, CALIBRATION_VARS, year, Log, calibration_counter, V, ftt_model=None):

    #region 2.2.01_Scenario_values [rgba(52,152,219,0.2)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.1] Read in Scenario values, updated dynamic variables
    # ^w        every iteration is a single year with dynamic variables defined in [2.1] carried over as starting values to the next year
    #endregion

    if self.mrio_inverse_recalculate:
        if 'Y_BASE' in EXOG_VARS.__dict__.keys():
            del EXOG_VARS.Y_BASE
        if 'L_BASE' in EXOG_VARS.__dict__.keys():
            del EXOG_VARS.L_BASE
        if 'G_BASE' in EXOG_VARS.__dict__.keys():
            del EXOG_VARS.G_BASE


    if year > self.model_start:
        # ^b [DYNAMICS]: update IO
        EXOG_VARS.IND_BASE = self.V.read_var_df('new_IO', year-1).set_index(['REG_imp','PROD_COMM','REG_exp','TRAD_COMM'])
        EXOG_VARS.HH_BASE = self.V.read_var('household_consumption', year-1, as_df=True).rename(columns={'household_consumption':'VIPA'}).set_index(['REG_imp','REG_exp','TRAD_COMM'])
        EXOG_VARS.FCF_BASE = self.V.read_var('fcf_consumption', year-1, as_df=True).rename(columns={'fcf_consumption':'VDFA'}).set_index(['REG_imp','REG_exp','TRAD_COMM'])
        EXOG_VARS.GOV_BASE = self.V.read_var('government_consumption', year-1, as_df=True).rename(columns={'government_consumption':'VIGA'}).set_index(['REG_exp','REG_imp','TRAD_COMM'])

    # Construct scenario module
    Scenario = scenario(EXOG_VARS, self.scenario_path, Log, year, self.years)
    Scenario.set_carbon_tax()

    # INITIALIZE VARIABLES
    if year == self.model_start:
        # TODO THIS IS NOT GOOD
        cap_stock = EXOG_VARS.CAPITAL_STOCK.copy()
        for y in [0,1,2,3]:
            cap_stock_yr = cap_stock.rename(columns={'capital_stock':'k'}).pipe(lambda d: d[d['year']==self.model_start-y]).drop(columns=['year'])
            self.V.write_var('k', year-y, cap_stock_yr, from_df=True)

        # INITIALIZE VA components
        # VA components are: compensation | profit | taxes
        # va_prev3 = EXOG_VARS.INITIAL_VA.pipe(lambda d: d[d['year']==year-3].copy())
        # DYNAMIC['value_added'][year-3] = va_prev3
        # va_prev2 = EXOG_VARS.INITIAL_VA.pipe(lambda d: d[d['year']==year-2].copy())
        # DYNAMIC['value_added'][year-2] = va_prev2
        va_prev1 = EXOG_VARS.INITIAL_VA.pipe(lambda d: d[d['year']==year-1].copy())
        DYNAMIC['value_added'][year-1] = va_prev1
        DYNAMIC['value_added'][year-2] = va_prev1
        DYNAMIC['value_added'][year-3] = va_prev1

        investment_by = EXOG_VARS.INVESTMENT_BY.rename(columns={'VDFA':'dk_base'}).pipe(lambda d: d[d['year']==self.model_start]).drop(columns=['year'])
        # TODO neither this is gooooood
        # ! we need to adjust investment (max 5% of capital stock in initial year)
        investment_by = investment_by.merge(self.V.read_var('k', year, as_df=True), how='right')
        sel_ = investment_by['dk_base'] > investment_by['k'] * 0.15
        investment_by.loc[sel_, 'dk_base'] = investment_by.loc[sel_, 'k'] * 0.15

        # ! add minimum investment if no investment
        sel_ = investment_by['dk_base'].isna()
        investment_by.loc[sel_, 'dk_base'] = investment_by.loc[sel_, 'k'] * 0.02

        self.V.write_var('dk_base', year-1, investment_by, from_df=True)
        self.V.write_var('dk_base', year, investment_by, from_df=True)
        # DYNAMIC['investment_vector'][year-1] = investment_by.copy()
        # DYNAMIC['investment_vector'][year] = investment_by.copy()

        DYNAMIC['govt_spending_delta'] = pd.DataFrame({'REG_imp':EXOG_VARS.R_list,'key':1}).merge(pd.DataFrame({'REG_exp':EXOG_VARS.R_list, 'key':1})).merge(pd.DataFrame({'TRAD_COMM':EXOG_VARS.P_list, 'key':1})).assign(VIGA = 0).drop(columns=['key'])
        _dp_zeros = np.zeros(len(EXOG_VARS.R_list) * len(EXOG_VARS.P_list))
        self.V.write_var('delta_price_yoy', year-1, _dp_zeros)
        self.V.write_var('delta_price_yoy', year-2, _dp_zeros)

        self.V.write_var('cpi', year-1, np.ones(len(EXOG_VARS.R_list)))
        _pi_ones = np.ones(len(EXOG_VARS.R_list) * len(EXOG_VARS.P_list))
        self.V.write_var('price_index', year-2, _pi_ones)
        self.V.write_var('price_index', year-1, _pi_ones)

        self.V.write_var('investment_price_index', year-1, self.V.read_var('price_index', year-1))

        q_prev = EXOG_VARS.INITIAL_Q.pipe(lambda d: d[d['year']==year-1].copy())
        self.V.write_var('output_current', year-1, q_prev.rename(columns={'q_base':'output_current'}), from_df=True)

        profit_rate = EXOG_VARS.INITIAL_Q.merge(EXOG_VARS.INITIAL_VA)
        profit_rate['profit_rate'] = profit_rate['profit'] / profit_rate['q_base']

        profit_rate_yr = {}
        for y in [(4,3),(3,3),(2,2),(1,1)]:
            profit_rate_yr[y[0]] = np.nan_to_num(MRIO_df_to_vec_DEF(profit_rate[profit_rate['year']==year-y[1]], 'profit_rate')) #type:ignore
            self.V.write_var("profit_rate", year-y[0], profit_rate_yr[y[0]])

        self.V.write_var('profit_rate_mean', year-1, (profit_rate_yr[4] + profit_rate_yr[3] + profit_rate_yr[2]) / 3)

        # ! initialize labour force, not sure it's good here
        # ! this should be 2017 and 2018, no?
        unemp_rate = EXOG_VARS.UNEMPLOYMENT_RATE[['REG_imp','Unemp_rate_18']].copy().rename(columns={'Unemp_rate_18':'unemployment_rate'})
        self.V.write_var("unemployment_rate", year-1, unemp_rate, from_df=True)
        unemp_rate = unemp_rate.rename(columns={'unemployment_rate':'shadow_unemployment_rate'})
        self.V.write_var("shadow_unemployment_rate", year-1, unemp_rate, from_df=True)
        labor = EXOG_VARS.LABOR_BASE.copy()
        labor['employment_base'] = labor[[x for x in labor.columns if x not in ['PROD_COMM','REG_imp'] and 'wage' not in x]].sum(axis=1)
        labor = labor[['REG_imp','PROD_COMM','employment_base']]
        self.V.write_var("employment_base", year-1, labor, from_df=True)

        national_employment = labor.groupby('REG_imp').agg({'employment_base':'sum'}).reset_index()
        shadow_nat_employment = national_employment.rename(columns={'employment_base':'shadow_nat_employment'})
        self.V.write_var('shadow_nat_employment', year-1, shadow_nat_employment, from_df=True)

        national_employment = national_employment.merge(self.V.read_var('unemployment_rate', year-1, as_df=True))
        national_employment['LF'] = national_employment['employment_base'] / (1 - national_employment['unemployment_rate'])
        self.V.write_var('labour_force', year-1, national_employment[['REG_imp','LF']].rename(columns={'LF':'labour_force'}), from_df=True)

        DYNAMIC['investment_converter'] = EXOG_VARS.set_inv_converter()
        self.V.write_var('inc_exog', year-1, np.zeros(len(EXOG_VARS.R_list)))

        # TODO add savings rate; compensation from VA and Spending from HH
        comp_0 = EXOG_VARS.INITIAL_VA.pipe(lambda d: d[d['year']==year-1].copy())[['REG_imp','compensation']]
        comp_0 = comp_0.groupby(['REG_imp']).agg({'compensation':'sum'}).reset_index()
        cons_0 = EXOG_VARS.HH_BASE.reset_index().groupby(['REG_imp']).agg({'VIPA':'sum'}).reset_index()
        saving = comp_0.merge(cons_0, how='left', on=['REG_imp'])
        saving['save_rate'] = 1 - saving['VIPA']/saving['compensation']
        self.V.write_var('save_rate', year-1, saving[['REG_imp','save_rate']], from_df=True)
        self.V.write_var('save_rate', year-2, saving[['REG_imp','save_rate']], from_df=True)
        self.V.write_var('save_rate', year-3, saving[['REG_imp','save_rate']], from_df=True)

        df = pd.DataFrame(columns=['REG_imp','PROD_COMM','TRAD_COMM','flow_price_impact_intermediates'])
        self.V.write_var('flow_price_impact_intermediates', year-2, df, from_df=True)
        self.V.write_var('flow_price_impact_intermediates', year-1, df, from_df=True)

        self.V.write_var('household_consumption', year-1, EXOG_VARS.HH_BASE.reset_index().rename(columns={'VIPA':'household_consumption'}), from_df=True)
        self.V.write_var('fcf_consumption', year-1, EXOG_VARS.FCF_BASE.reset_index().rename(columns={'VDFA':'fcf_consumption'}), from_df=True)
        self.V.write_var('government_consumption', year-1, EXOG_VARS.GOV_BASE.reset_index().rename(columns={'VIGA':'government_consumption'}), from_df=True)


    population = EXOG_VARS.POPULATION.rename(columns={'Agg_region':'REG_imp'})[['REG_imp','year','value']]
    population['YoY_change_POP'] = population['value'] / population.groupby('REG_imp')['value'].shift(1)

    LPR = EXOG_VARS.LABOUR_FORCE_PARTICIPATION.rename(columns={'Agg_region':'REG_imp'})[['REG_imp','year','value']]
    LPR['YoY_change_LPR'] = LPR['value'] / LPR.groupby('REG_imp')['value'].shift(1)

    labour_force = self.V.read_var('labour_force', year-1, as_df=True).rename(columns={'labour_force':'LF'}).merge(population.query("year == @year"), how='left', on=['REG_imp'])
    labour_force = labour_force.merge(LPR.query("year == @year"), how='left', on=['REG_imp'])
    labour_force['LF'] = labour_force['LF'] * labour_force['YoY_change_POP'] * labour_force['YoY_change_LPR']

    ##########################################
    # START >>>>>>> ONLY FOR IFC GENDER
    ##########################################

    # if year > self.model_start:
    #     output = MRIO_vec_to_df_DEF(DYNAMIC['output'][year-1], 'q').query("PROD_COMM == 117 | PROD_COMM == 118")
    #     output_prev = MRIO_vec_to_df_DEF(DYNAMIC['output'][year-2], 'q_prev').query("PROD_COMM == 117 | PROD_COMM == 118")

    #     output = output.merge(output_prev, how='left', on=['REG_imp','PROD_COMM'])
    #     output = output.groupby(['REG_imp']).agg({'q':'sum','q_prev':'sum'}).reset_index()

    #     output['delta'] = (output['q'] / output['q_prev']) - 1.0
    #     # ! limit to 1/3 growth or increase
    #     output['delta'] = output['delta'].apply(lambda x: x if abs(x) < 0.3 else 0.3 * (x/abs(x)))
    #     output['delta'] = output['delta'] * 0.33

    #     labour_force = labour_force[['REG_imp','LF']].copy()
    #     labour_force = labour_force.merge(output[['REG_imp','delta']], how='left', on='REG_imp')
    #     labour_force['LF'] = labour_force['LF'] * (1 + labour_force['delta'])

    ##########################################
    # END >>>>>>> ONLY FOR IFC GENDER
    ##########################################

    self.V.write_var('labour_force', year, labour_force[['REG_imp','LF']].rename(columns={'LF':'labour_force'}), from_df=True)

    # INITIALIZE OUTPUT
    # ! this doesn't work because GLORIA data for 2018 vs 2019 is crazy (i.e 120 sector rest of world (excl USA all others))
    # ! is like X4 of (2019 * 4 = 2018/2017), so we basically get an output gap of 75% ...
    # ! therefore this is not good, but a workable solution; we set normal output to observed for first year
    # if year == self.model_start:
        # q_base_prev3 = EXOG_VARS.INITIAL_Q.pipe(lambda d: d[d['year']==year-3].copy())
        # DYNAMIC['q_base_prev3'] = MRIO_df_to_vec_DEF(q_base_prev3,"q_base")
        # q_base_prev2 = EXOG_VARS.INITIAL_Q.pipe(lambda d: d[d['year']==year-2].copy())
        # DYNAMIC['q_base_prev2'] = MRIO_df_to_vec_DEF(q_base_prev2,"q_base")
        # q_base_prev1 = EXOG_VARS.INITIAL_Q.pipe(lambda d: d[d['year']==year-1].copy())
        # DYNAMIC['q_base_prev1'] = MRIO_df_to_vec_DEF(q_base_prev1,"q_base")
        # DYNAMIC['qavg'] = (DYNAMIC['q_base_prev3'] + DYNAMIC['q_base_prev2'] + DYNAMIC['q_base_prev1']) / 3
    # ! moved down to line 551

    # INITIALIZE NORMAL OUTPUT
    # first year normal output is simply average of Q over last 3 years
    # ! this doesn't work because GLORIA data for 2018 vs 2019 is crazy (i.e 120 sector rest of world (excl USA all others))
    # ! is like X4 of (2019 * 4 = 2018/2017), so we basically get an output gap of 75% ...
    # ! therefore this is not good, but a workable solution; we set normal output to observed for first year
    # if year == self.model_start:
        # normal_output = MRIO_vec_to_df_DEF(DYNAMIC['qavg'], 'normal_output')
        # DYNAMIC['normal_output'] = normal_output
    # ! moved down to line 551

    print("--- 2.2.1 Exogenous variables: %s seconds ---" % round(time.time() - self.module_time, 1))

    #endregion

    #region 2.2.03_Set_shocks_from_scenario [rgba(52,152,219,0.2)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.3] Set shocks from scenario (if any)      
    # ^w        this part reads in revenue recycling stuff for the scenario as well as cost shock, exogenous investment and supply constraints
    #endregion

    rev_split = Scenario.build_rev_split()
    rev_proportion = Scenario.build_rev_proportion()
    govt_spending = Scenario.build_govt_spending()
    inv_spending = Scenario.build_inv_spending()

    io_changes = Scenario.set_io_changes()
    Scenario.set_cost_shock()
    # Scenario.set_exog_inv(DYNAMIC['investment_vector'][year])
    Scenario.set_exog_inv(self.V.read_var('dk_base', year, as_df=True))
    self.V.write_var('inc_exog', year, Scenario.set_exog_inc().rename(columns={'dlabor_exog':'inc_exog'}), from_df=True)
    Scenario.set_supply_constraint()
    Scenario.set_supply_constraint_no_empl()
    Scenario.set_capital_stock_change()
    Scenario.set_exog_ener_intensity()

    # ! adjust capital stock, let's put this somewhere else later
    # ! only in scenario
    if not CALIBRATING:
        cap_stock_adjust = self.V.read_var('k', year, as_df=True).merge(Scenario.capital_change.query("Type == 'rel'"), on=['REG_imp','PROD_COMM'], how='left')
        cap_stock_adjust['Value'] = cap_stock_adjust['Value'].fillna(0)
        cap_stock_adjust['k'] = cap_stock_adjust['k'] * (1 + cap_stock_adjust['Value'])
        self.V.write_var('k', year, cap_stock_adjust[['REG_imp','PROD_COMM','k']], from_df=True)


    #endregion  

    #region 2.2.06_Re-calculate_IO [rgba(52,152,219,0.2)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.6] Re-calculate IO table and calculate prices
    # ^w        first, the IO changes due to technology substitution [2.2.4] here
    # ^w        second, we calculate prices based on these
    #endregion

    module_time = time.time()

    # Construct Input-Output model
    IO_model = IO(EXOG_VARS)
    if year == self.model_start:
        IO_model.initialize()
        output_1 = np.nan_to_num(IO_model.q_base / self.initial_g, posinf=0, neginf=0)
        output_2 = np.nan_to_num(output_1 / self.initial_g, posinf=0, neginf=0)
        output_3 = np.nan_to_num(output_2 / self.initial_g, posinf=0, neginf=0)
        self.V.write_var("output", year-1, output_1)
        self.V.write_var("output", year-2, output_2)
        self.V.write_var("output", year-3, output_3)
    else:
        IO_model.initialize(self.V.read_var("output", year-1))

    # ! TEMPORARY, need OUTPUT GAP
    if year == self.model_start:
        normal_output_1 = MRIO_vec_to_df_DEF(self.V.read_var("output", year-1) * 1.028, 'normal_output')
        normal_output_2 = MRIO_vec_to_df_DEF(self.V.read_var("output", year-2) * 1.028, 'normal_output')
        helper = MRIO_vec_to_df_DEF(self.V.read_var("output", year-2) * 1.028 * self.initial_g, 'normal_output')

        self.V.write_var('normal_output', year-1, normal_output_1, from_df=True)
        self.V.write_var('normal_output', year-2, normal_output_2, from_df=True)

        self.V.write_var('normal_output_growth_helper', year-1, helper['normal_output'].values)
        self.V.write_var('normal_output_growth_helper', year-2, normal_output_2['normal_output'].values)

    # ! so this here corrects for the fact that output at the end of t-1
    # ! is a combination of q_base + dq_total and q_base_curr is what's the output given the current IO and total FD
    # ! if output was higher last year that might disappear becase IO has changed
    # ! a further issue is supply restrictions; we werent able to produce but the demand is there
    dq_structural_change = IO_model.q_base_curr - self.V.read_var("output", year-1)
    # - DYNAMIC['dq_exog_hh_prev'] - DYNAMIC['dq_exog_gov_prev'] - DYNAMIC['dq_exog_fcf_prev'])
    dq_structural_change_wo_employment = dq_structural_change + DYNAMIC['dq_supply_constraint_no_empl']

     # ? dq_structural_changr is equal to unmet_demand (production side in the last year)

    print("--- 2.2.6 IO initialisation: %s seconds ---" % round(time.time() - module_time, 1))
    #endregion

    #region 2.2.02_Carbon_tax_incidence [rgba(52,152,219,0.1)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.2] Calculate carbon tax incidence (if any)      
    # ^w        using the energy/emission network read in in EXOG_VARS we initialize the Energy_emissions module
    # ^w        this part also calculates carbon tax incidences
    # ^w
    # TODO  CARBON tax incidence is currently limited to 1000, as in 1000% of the original price
    # TODO  Energy_emission and Ener_model can be consolidated
    #endregion

    module_time = time.time()

    Energy_emissions = ener_balance(EXOG_VARS, Scenario, self.refining_sectors)
    if year == self.model_start:
        DYNAMIC['carbon_content'] = Energy_emissions.calc_emission_intensities()
        DYNAMIC['carbon_content_process'] = Energy_emissions.calc_emission_intensities_process()
        DYNAMIC['fuel_price'] = Energy_emissions.calc_fuel_implicit_price()
    if year == self.model_start:
        helper = ['FD_1','FD_3','FD_4']
        self.V.write_var('fuel_implicit_price',year,DYNAMIC['fuel_price'].query("PROD_COMM != @helper").rename(columns={'implicit_price':'fuel_implicit_price'}).astype({"PROD_COMM":'int'}),from_df=True)
        self.V.write_var('fuel_implicit_price_fd',year,DYNAMIC['fuel_price'].query("PROD_COMM == @helper").rename(columns={"PROD_COMM":'FD','implicit_price':'fuel_implicit_price_fd'}),from_df=True)

    ctax_price_impact_prev = self.V.read_var('flow_price_impact_intermediates', year-2, as_df=True)
    ctax_price_impact_prev = ctax_price_impact_prev.rename(columns={'flow_price_impact_intermediates':'ctax_price_impact_2'})
    ctax_price_impact = self.V.read_var('flow_price_impact_intermediates', year-1, as_df=True)
    ctax_price_impact = ctax_price_impact.rename(columns={'flow_price_impact_intermediates':'ctax_price_impact_1'})
    ctax_price_impact = ctax_price_impact_prev.merge(ctax_price_impact, how='outer').fillna(0)
    ctax_price_impact['ctax_price_impact'] = ctax_price_impact['ctax_price_impact_1'] - ctax_price_impact['ctax_price_impact_2']
    ctax_price_impact.loc[ctax_price_impact['ctax_price_impact'] > 5.0, 'ctax_price_impact'] = 5.0
    ctax_price_impact.loc[ctax_price_impact['ctax_price_impact'] < -5.0, 'ctax_price_impact'] = -5.0
    ctax_price_impact = ctax_price_impact.drop(columns=['ctax_price_impact_1','ctax_price_impact_2'])

    # Zero out delta_price_yoy for sectors whose output was already 0 in year-1.
    # model_class zeroes delta_price_yoy[year] for newly-dead sectors, but as a
    # safety net we also suppress the price signal for any already-dead sector so
    # that zero-fuel-use rows don't pick up a ghost substitution signal.
    _dp_raw = self.V.read_var('delta_price_yoy', year-1)
    _out_prev_for_dp = self.V.read_var('output', year-1)
    _dp_raw[_out_prev_for_dp == 0] = 0.0

    Energy_emissions.load_dynamic({
        'price_index': self.V.read_var('price_index', year-1, as_df=True),
        'other_vars': DYNAMIC['other_country_vars'],
        'delta_price_yoy': MRIO_vec_to_df_DEF(_dp_raw, 'dp'),
        'carbon_content': DYNAMIC['carbon_content'],
        'carbon_content_process': DYNAMIC['carbon_content_process'],
        'fuel_price': DYNAMIC['fuel_price'],
        'ctax_price_impact': ctax_price_impact
    })

    # calculate energy_flows based on the IO table and implicit prices stored from the first year
    ener_base = Energy_emissions.calc_fuel_prod_base()
    ener_base_interm = ener_base[~ener_base['PROD_COMM'].str.contains("FD")].copy()
    ener_base_interm['PROD_COMM'] = ener_base_interm['PROD_COMM'].astype(int)
    self.V.write_var_df('energy_flows', year, ener_base_interm)

    ener_base_fd = ener_base[ener_base['PROD_COMM'].str.contains("FD")].copy()
    ener_base_fd = ener_base_fd.rename(columns={'PROD_COMM': 'FD'})
    self.V.write_var_df('energy_flows_fd', year, ener_base_fd)

    if year > self.model_start:
        Energy_emissions.calc_energy_efficiency(self.V.read_var_df('energy_flows', year), self.V.read_var("output", year-1, as_df=True).rename(columns={'output':'q_base'}))
        ener_change = Energy_emissions.calc_fuel_substitution(
            self.V.read_var_df('energy_flows', year),
            self.V.read_var("output", year-1, as_df=True).rename(columns={'output':'q_base'}),
            self.V.read_var("output", year-2, as_df=True).rename(columns={'output':'q_prev'})
            )
        # DYNAMIC['energy_flows'][year] = ener_change['energy_flows']

        # the dy effect is going to be IO based
        # ---> we assume that Q is unchanged, but energy still changes
        # ---> but this changes Q for energy

        # adjust IO
        ind_energy = Energy_emissions.calc_monetary_io_change(ener_change['io_impact'])
        A_energy = IO_model.build_A_matrix(input_df=ind_energy, variable='IO_coef_ener')
        # calculate IO impact
        IO_model.update_Leontieff(A_energy)
        dq_tech_eff = IO_model.calc_dq_energy_subst(A_energy)
        Energy_emissions.update_ind_base(A_energy, self.V.read_var("output", year-1) + dq_tech_eff)

    else:
        dq_tech_eff = np.zeros((len(EXOG_VARS.R)*len(EXOG_VARS.P)))
        ind_energy = EXOG_VARS.IND_BASE.rename(columns={'z_bp':'z_bp_ener'})
    self.V.write_var("dq_tech_eff", year, dq_tech_eff)
        
    tax_incidence = Energy_emissions.calculate_tax_incidence()
    # Store as local dicts — written to V only inside the iteration loop (or at end if loop is skipped)
    emission_cost_dfs = {
        'intermediates': tax_incidence['tax_incidence_intermediates'],
        'hh':            tax_incidence['tax_incidence_hh'],
        'fcf':           tax_incidence['tax_incidence_fcf'],
        'gov':           tax_incidence['tax_incidence_gov'],
    }

    flow_price_impact_intermediates = tax_incidence['flow_price_impact_intermediates']
    flow_price_impact_hh = tax_incidence['flow_price_impact_hh']
    flow_price_impact_hh.loc[flow_price_impact_hh['flow_price_impact_hh']> 5, 'flow_price_impact_hh'] = 5.0

    self.V.write_var('flow_price_impact_intermediates', year, flow_price_impact_intermediates, from_df=True)
    self.V.write_var('flow_price_impact_hh', year, flow_price_impact_hh.rename(columns={'PROD_COMM': 'FD'}), from_df=True)

    BTA_cou = BTA(Scenario, self.bta, EXOG_VARS.R, self.temp, EXOG_VARS)
    if year > self.model_start:
        cbam_incidence = BTA_cou.calc_cbam_incidence(ind_energy, DYNAMIC['carbon_content'], EXOG_VARS.HH_BASE, EXOG_VARS.FCF_BASE, EXOG_VARS.GOV_BASE)
    else:
        cbam_incidence = BTA_cou.calc_cbam_incidence(EXOG_VARS.IND_BASE, DYNAMIC['carbon_content'], EXOG_VARS.HH_BASE, EXOG_VARS.FCF_BASE, EXOG_VARS.GOV_BASE)
    # cbam incidence ['REG_imp','REG_exp','PROD_COMM','TRAD_COMM','cbam_cost']
    cbam_cost_dfs = {
        'intermediates': cbam_incidence[~cbam_incidence['PROD_COMM'].str.contains("FD")].copy().astype({'PROD_COMM': int, 'TRAD_COMM': int}),
        'hh':            cbam_incidence[cbam_incidence['PROD_COMM']=="FD_1"].copy(),
        'fcf':           cbam_incidence[cbam_incidence['PROD_COMM']=="FD_4"].copy(),
        'gov':           cbam_incidence[cbam_incidence['PROD_COMM']=="FD_3"].copy(),
    }

    # # limit carbon tax to 1000% tax rate
    # carbon_tax['delta_tax'] = carbon_tax['delta_tax'].apply(lambda x: x if x < 10 else 10) # type: ignore

    # Scenario.set_tax_rate(carbon_tax)
    # tax_rate, tax_rate_hh = Scenario.assign_price_change(Scenario.tax_rate, Scenario.tax_rate_hh, Scenario.cost_shock)
    tax_rate = pd.DataFrame(columns=['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','delta_tax'])
    tax_rate_hh = pd.DataFrame(columns=['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','delta_tax_hh'])

    print("--- 2.2.2 Carbon tax incidence: %s seconds ---" % round(time.time() - module_time, 1))

    #endregion

    #region 2.2.05_Tax_revenues_&_CBAM [rgba(52,152,219,0.2)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.5] Calculation of tax revenues and CBAM impact  
    # ^w        first, we add the CBAM effect to the calculation
    # ^w        then, tax revenues are calculated, we calculate two type of revenues base and actual -- ??
    # ^w
    # TODO  why we calculate tax revenue base?
    # TODO  does the CBAM treatment currently makes sense? 
    #endregion

    module_time = time.time()
    # Construct tax revenue module
    Tax_rev = tax_rev_mod(EXOG_VARS, None, bta=self.bta)
    Tax_rev.load_dynamic({
        'price_index': self.V.read_var('price_index', year-1, as_df=True)
    })

    # tax_rev_cou_base = Tax_rev.calc_tax_rev_base(tax_rate)
    # tax_rev_cou = Tax_rev.calc_tax_rev(tax_rate, ind_ener_cou)

    # tax_rev_hh_base = Tax_rev.calc_tax_rev_hh_base(tax_rate_hh)
    # tax_rev_hh = Tax_rev.calc_tax_rev_hh(tax_rate_hh)
    # ! CPRICE tax revenue is emission_cost across all types
    tax_rev_interm = emission_cost_dfs['intermediates'].groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev'})
    tax_rev_hh = emission_cost_dfs['hh'].groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev_hh'})
    tax_rev_fcf = emission_cost_dfs['fcf'].groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev_fcf'})
    tax_rev_gov = emission_cost_dfs['gov'].groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev_gov'})

    cbam_interm = cbam_cost_dfs['intermediates'].groupby(['REG_imp']).agg({'cbam_cost':'sum'}).reset_index().rename(columns={'cbam_cost':'cbam_rev'})
    cbam_hh =  cbam_cost_dfs['hh'].groupby(['REG_imp']).agg({'cbam_cost':'sum'}).reset_index().rename(columns={'cbam_cost':'cbam_rev_hh'})
    cbam_fcf = cbam_cost_dfs['fcf'].groupby(['REG_imp']).agg({'cbam_cost':'sum'}).reset_index().rename(columns={'cbam_cost':'cbam_rev_fcf'})
    cbam_gov =  cbam_cost_dfs['gov'].groupby(['REG_imp']).agg({'cbam_cost':'sum'}).reset_index().rename(columns={'cbam_cost':'cbam_rev_gov'})

    tax_rev = tax_rev_interm.merge(tax_rev_hh, how='outer', on=['REG_imp']).merge(tax_rev_fcf, how='outer', on='REG_imp').merge(tax_rev_gov, how='outer', on='REG_imp')
    tax_rev = tax_rev.merge(cbam_interm, how='outer', on=['REG_imp']).merge(cbam_hh, how='outer', on='REG_imp').merge(cbam_fcf, how='outer', on='REG_imp')
    tax_rev = tax_rev.merge(cbam_gov, how='outer', on='REG_imp')
    tax_rev = tax_rev.fillna(0)
    tax_rev['tax_rev'] = tax_rev['tax_rev'] + tax_rev['tax_rev_hh'] + tax_rev['tax_rev_fcf'] + tax_rev['tax_rev_gov']
    tax_rev['tax_rev'] = tax_rev['tax_rev'] + tax_rev['cbam_rev'] + tax_rev['cbam_rev_hh'] + tax_rev['cbam_rev_fcf'] + tax_rev['cbam_rev_gov']
    tax_rev = tax_rev[['REG_imp','tax_rev']].copy()

    # Calculate revenue recycled into different schemes (base and after energy elasticities)
    if year > self.model_start:
        recyc_rev_base = Tax_rev.calc_recyc_rev(tax_rev, rev_split)
        DYNAMIC['carbon_tax_revenues'][year] = recyc_rev_base.copy()
        recyc_rev_base = Tax_rev.subtract_prev(recyc_rev_base, DYNAMIC['carbon_tax_revenues'][year-1])
    else:
        recyc_rev_base = Tax_rev.calc_recyc_rev(tax_rev, rev_split)
        DYNAMIC['carbon_tax_revenues'][year] = recyc_rev_base.copy()
    # recyc_rev = Tax_rev.calc_recyc_rev(
        # tax_rev_prod, tax_rev_hh, rev_subtract_exp, rev_split)

    print("--- 2.2.5 Tax revenue: %s seconds ---" % round(time.time() - module_time, 1))
    module_time = time.time()

    #endregion

            # Construct price model
    Price_model = price(EXOG_VARS, IO_model, BTA_cou)


    #region 2.2.04_Technology_substitution [rgba(52,152,219,0.1)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.4] Technology substitution due to price effect for energy products      
    # ^w        we use energy elasticities (cross- and own-price) to reallocate energy demand based on price effects
    # ^w        energy is the only technology where we allow substitution across products
    #endregion

    module_time = time.time()
    # Construct energy elasticities module
    Ener_model = ener_elas(EXOG_VARS)
    # Build energy elasticities dataframe and assign tax rate information
    # Ener_model.build_ener_elas()
    Ener_model.load_dynamic({
        'delta_price_yoy': MRIO_vec_to_df_DEF(self.V.read_var('delta_price_yoy', year-1), 'dp')
    })

    # ? tech effect is dependent on
    # ? --> (1) price changes last year on the producer side ---> DYNAMIC['dp_prev1']
    # ? --> (2) my cost of using a given flow, which is the tax I would have to pay for the flow based on last years emissions; DYNAMIC['tax_rate_prev']
    # ? 
    # ? --> total energy consumption can change (energy efficiency)
    # ? --> energy volume reacts not value
    
    Ener_model.assign_price_change()

    # Calculate technical and IO coefficients due to energy elasticities
    # tech_coef_ener = Ener_model.calc_tech_coef_ener()
    # ind_ener_cou = Ener_model.assign_IO_coef_cou(tech_coef_ener)
    # ind_ener_glo = Ener_model.assign_IO_coef_glo(ind_ener_cou)
    if year > self.model_start:
        ind_ener_glo = ind_energy
    else:
        ind_ener_glo = ind_energy.rename(columns={'z_bp':'z_bp_ener','a_bp':'IO_coef_ener'})
        # ind_energy.to_csv(f"ind_energy_{year}.csv")

    # Build helper matrices for energy commodities
    # tax_index, tax_matrix, sec_matrix = Ener_model.build_tax_helper_matrix(ind_ener_cou)

    # Calculate changes in Leontief matrix for energy commodities
    # dL_ener = IO_model.build_dL_ener(tax_index, tax_matrix, sec_matrix)

    print("--- 2.2.4 Technology substitution: %s seconds ---" % round(time.time() - module_time, 1))

    #endregion

    #region 2.2.07_Production_costs [rgba(52,152,219,0.1)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.7] Production cost and labor comp. calculation  
    # ^w        calculate production costs and update employment and labor comp [dynamics]
    #endregion

    # Construct production module (exogenous production cost)
    Prod_cost = prod_cost(EXOG_VARS, Scenario)
    Prod_cost.load_dynamic({
        'q_base': self.V.read_var("output", year-1, as_df=True).rename(columns={'output':'q_base'}),
        'price_index': self.V.read_var('price_index', year-1, as_df=True)
    })

    if year > self.model_start:
        # dynamic employment such as: empl_base_t=1 = empl_base_t=0 + dempl_total_t=0
        # REG_imp | PROD_COMM | employment_base
        # Prod_cost.empl_base = self.V.read_var('employment_base', year-1, as_df=True)
        Prod_cost.labor_comp = DYNAMIC['new_labor_comp']
    else:
        Prod_cost.calc_initial()

    Empl_model = empl(EXOG_VARS, self.cost_curve_employment)

    if year == self.model_start:
        employment_base = Empl_model.calc_initial()
        self.V.write_var("employment_base", year, employment_base, from_df=True)

    Inc_model = income(EXOG_VARS, Prod_cost)
    if year == self.model_start:
        Inc_model.load_dynamic({
            'employment_base': self.V.read_var('employment_base', year, as_df=True)
        })
        Inc_model.calc_wage()
        self.V.write_var('wage', year-1, Inc_model.wage, from_df=True)
        self.V.write_var('wage', year, Inc_model.wage, from_df=True)
    else:
        Inc_model.load_dynamic({
            'wage_prev': self.V.read_var('wage', year-2, as_df=True), # wage from prev year
            'wage': self.V.read_var('wage', year-1, as_df=True), # starting wage (end of last year)
            'cpi': self.V.read_var('cpi', year-1, as_df=True), # cpi this is change in consumer prices, i.e 1.2 20% from last year; it's NOT index
            'cpi_prev': self.V.read_var('cpi', year-2, as_df=True),
            'd_productivity': np.nan_to_num(self.V.read_var('productivity', year-1) / self.V.read_var('productivity', year-2) -1, posinf=0, neginf=0),
            'employment_base': self.V.read_var('employment_base', year, as_df=True),
            'unemployment_rate': self.V.read_var('shadow_unemployment_rate', year-1, as_df=True).rename(columns={'shadow_unemployment_rate':'unemployment_rate'}),
            'unemployment_rate_prev': self.V.read_var('unemployment_rate', year-2, as_df=True)
        })
        Inc_model.calc_wage(econometrics=True)
        self.V.write_var('wage', year, Inc_model.wage, from_df=True)

    if year == self.model_start:
        # ^b CALC PRODUCTIVITY
        prod = np.nan_to_num(self.V.read_var("output", year-1) / self.V.read_var('employment_base', year), posinf=0, neginf=0)
        self.V.write_var('productivity', year-1, prod)
        self.V.write_var('productivity', year-2, prod)

    # ! start with ENDOGENOUS price changes: i.e., normal output and deviation from profit based

    Price_model.calc_positive_and_negative_L()

    # ! carbon price, only intermediates!
    if year == self.model_start:
        emission_cost = emission_cost_dfs['intermediates'].groupby(['REG_imp','PROD_COMM']).agg({'emission_cost':'sum'}).reset_index()
    else:
        emission_cost = emission_cost_dfs['intermediates'].groupby(['REG_imp','PROD_COMM']).agg({'emission_cost':'sum'}).reset_index()
        emission_cost_prev = self.V.read_var_df('emission_cost_intermediates', year-1).groupby(['REG_imp','PROD_COMM']).agg({'emission_cost':'sum'}).reset_index()
        emission_cost = emission_cost.merge(emission_cost_prev.rename(columns={'emission_cost':'prev'}), how='outer').fillna(0)
        emission_cost['emission_cost'] = emission_cost['emission_cost'] - emission_cost['prev']
        emission_cost = emission_cost.drop(columns=['prev'])
    v_ctax = Prod_cost.calc_prod_cost_impact(MRIO_df_to_vec_DEF(emission_cost, 'emission_cost'))
    # ! limit ctax to 300% price increase
    v_ctax[v_ctax > 3.0] = 3.0
    ctax_effect = Price_model.second_order_dprice(v_ctax, direct_impact="passthrough")
    dp_ctax = ctax_effect['dp_full']
    v_ctax = ctax_effect['v_calculated']

    # ! output volume growth
    if year == self.model_start:
        output_growth_L1 = np.zeros_like(self.V.read_var("output", year-1))
    else:
        output_growth_L1 = np.nan_to_num(self.V.read_var("output", year-1) / self.V.read_var("output", year-2), posinf=0, neginf=0) - 1
    v_output_growth = Price_model.dp_output_growth(output_growth_L1)
    dp_output_growth = Price_model.second_order_dprice(v_output_growth)['dp_full']

    # ! deviation from normal output (last year) 
    # ! ----> DYNAMIC['normal_output'] is normal output last year : PROD_COMM | REG_imp | normal_output
    # ! ----> DYNAMIC['new_qbase'] is observed output last year : this is a vector
    normal_output_L1 = self.V.read_var('normal_output', year-1)
    observed_output_L1 = self.V.read_var("output", year-1)
    if year == self.model_start:
        dev_normal_output_L1 = np.zeros_like(self.V.read_var("output", year-1))
    else:
        dev_normal_output_L1 = np.nan_to_num(observed_output_L1 / normal_output_L1 - 1, posinf=0, neginf=0)
    dev_normal_output_L1[(abs(dev_normal_output_L1)==np.inf) | (abs(dev_normal_output_L1) > 100)] = 0
    v_dev_normal_output = Price_model.dp_normal_output(dev_normal_output_L1) # this is the 1st order price impact by sector
    # ! we then need to calculate the 2nd order effect; calculation includes both direct and 2nd order effects
    dp_dev_normal_output = Price_model.second_order_dprice(v_dev_normal_output)['dp_full']

    # ! profit deviation
    profit_rate_L1 = self.V.read_var('profit_rate', year-1)
    
    # ! first year limit deviation
    if year == self.model_start:
        _prm = self.V.read_var('profit_rate_mean', year-1)
        correction = np.nan_to_num(profit_rate_L1 - _prm)
        # we only correct if diff larger than 5pp; in these cases replace mean rate with current rate +- 5pp
        _prm[correction > 0.05] = profit_rate_L1[correction > 0.05] - 0.05
        _prm[correction < 0.05] = profit_rate_L1[correction < 0.05] + 0.05

    # TODO treat negative
    # ! limit profit rate difference in first year
    profit_rate_mean_L1 = self.V.read_var('profit_rate_mean', year-1)
    if year > self.model_start:
        profit_rate_mean_L1 = MRIO_vec_to_df_DEF(self.V.read_var('profit_rate_mean', year-1), 'profit_rate')
        profit_rate_mean_L1 = profit_rate_mean_L1.merge(DYNAMIC['other_country_vars'], how='left', on=['REG_imp'])

        # ? so we calculate a minimum profit rate that 'necessary' to yield returns that in line of expectations (i.e. interest rates)
        # ? the AI (Claude) tells me this is similar to a Sraffian concept
        # ? we need: depreciation_rate; capital stock; output and interest rate
        # ? capital_stock -> 'k'
        # ? output -> 'output'
        # ? depr_rate -> 'depreciation_rate'
        depr_rate = self.V.read_var("depreciation_rate", year-1, as_df=True)
        depr_rate['capital_stock'] = self.V.read_var("k", year-1)
        depr_rate['output'] = self.V.read_var("output", year-1)
        profit_rate_mean_L1 = profit_rate_mean_L1.merge(depr_rate, how='left', on=['REG_imp','PROD_COMM'])

        profit_rate_mean_L1['profit_rate_min'] = profit_rate_mean_L1['interest_rate'] * (1 + profit_rate_mean_L1['depreciation_rate'] * profit_rate_mean_L1['capital_stock']/profit_rate_mean_L1['output']) / (1 + profit_rate_mean_L1['interest_rate'])
        profit_rate_mean_L1.loc[profit_rate_mean_L1['profit_rate_min'] > 0.95, 'profit_rate_min'] = 0.95
        self.V.write_var("profit_rate_min", year, profit_rate_mean_L1[['PROD_COMM','REG_imp','profit_rate_min']], from_df=True)

        # ! only works with 120 sectors now
        sel = (profit_rate_mean_L1['profit_rate'] < profit_rate_mean_L1['profit_rate_min']) & (~(profit_rate_mean_L1['PROD_COMM'].isin([115,116,117,118])))
        profit_rate_mean_L1.loc[sel, 'profit_rate'] = profit_rate_mean_L1['profit_rate_min']
        profit_rate_mean_L1 = profit_rate_mean_L1['profit_rate'].values
    dev_profit_rate_L1 = np.nan_to_num(profit_rate_L1 - profit_rate_mean_L1)
    
    dev_profit_rate_L1[abs(dev_profit_rate_L1)==np.inf] = 0.0
    dev_profit_rate_L1[abs(dev_profit_rate_L1)>10] = 0.0
    v_dev_profit_rate = Price_model.dp_profit_rate(dev_profit_rate_L1)
    dp_dev_profit_rate = Price_model.second_order_dprice(v_dev_profit_rate, year=year)['dp_full']
    
    # TODO
    # ! scarcity rent
    # ? dq_structural_changr is equal to unmet_demand (production side in the last year)
    if year > self.model_start:
        output = self.V.read_var("output", year-1)
        underproduction = dq_structural_change / output
        underproduction[output == 0.0] = 0
        underproduction[underproduction <= 0.0] = 0.0
        scarcity_rent = underproduction * 0.84
        # apply elasticity from Hallegatte (2008), 0.07% by month, 0.84% by year
    else:
        scarcity_rent = np.zeros_like(self.V.read_var("output", year-1))
    v_scarcity_rent = np.nan_to_num(scarcity_rent)
    dp_scarcity_rent = Price_model.second_order_dprice(v_scarcity_rent)['dp_full']


    # ! prod_cost considering both TAX change
    # exog_prod_cost = Prod_cost.calc_prod_cost(tax_rev_prod_base, recyc_rev_base)
    # v_tax = MRIO_df_to_vec_DEF_1(exog_prod_cost, 'prod_cost_rel')
    # v_tax = v_tax - 1
    
    # ! non-tax type price change (no recycling, no energy substitution)
    # ! this only has demand effects!
    exog_prod_cost = Prod_cost.prod_cost_impact(Scenario.cost_shock)
    v_exog = MRIO_df_to_vec_DEF(exog_prod_cost, 'Value')
    dp_exog = Price_model.second_order_dprice(v_exog)['dp_full']

    # ! calculate labor changes here(!!!)
    if year > self.model_start and self.SWITCH_WITHIN_YEAR_LOOP:
        dlabor_sec = Inc_model.recalc_labor_comp_delta()
        dlabor_sec = dlabor_sec.rename(columns={'glabor':'dlabor'})
        dlabor_nat = dlabor_sec.groupby(["REG_imp"])["dlabor"].sum()

        # ! add labor cost impacts
        exog_prod_cost_w_labor = Prod_cost.calc_labor_cost_impact(
            self.V.read_var('price_index', year-1, as_df=True),
            self.V.read_var("output", year-1, as_df=True).rename(columns={'output':'q_base'}),
            dlabor_sec)
        v_labor = MRIO_df_to_vec_DEF(exog_prod_cost_w_labor, 'prod_cost_rel')
        labor_eff = Price_model.second_order_dprice(v_labor, year=year, direct_impact="passthrough")
        dp_labor = labor_eff['dp_full']
        v_labor = labor_eff['v_calculated']
    else:
        v_labor = np.zeros_like(v_exog)
        dp_labor = np.zeros_like(dp_exog)

    # dL_ener is generally memory heavy so calculate, than store to Temp, then delete and collect garbage
    # del dL_ener
    gc.collect()

    # ! price effects from CBAM instant 
    # ! THIS IS CURRENTLY FULL PASS THROUGH!!!!
    # ! carbon price, only intermediates!

    if year == self.model_start:
        cbam_cost = cbam_cost_dfs['intermediates'].groupby(['REG_imp','PROD_COMM']).agg({'cbam_cost':'sum'}).reset_index()
    else:
        cbam_cost = cbam_cost_dfs['intermediates'].groupby(['REG_imp','PROD_COMM']).agg({'cbam_cost':'sum'}).reset_index()
        cbam_cost_prev = self.V.read_var_df('cbam_cost_intermediates', year-1).groupby(['REG_imp','PROD_COMM']).agg({'cbam_cost':'sum'}).reset_index()
        cbam_cost = cbam_cost.merge(cbam_cost_prev.rename(columns={'cbam_cost':'prev'}), how='outer').fillna(0)
        cbam_cost['cbam_cost'] = cbam_cost['cbam_cost'] - cbam_cost['prev']
        cbam_cost = cbam_cost.drop(columns=['prev'])
    v_cbam = Prod_cost.calc_prod_cost_impact(MRIO_df_to_vec_DEF(cbam_cost, 'cbam_cost'))
    # ! limit ctax to 300% price increase
    v_cbam[v_cbam > 3.0] = 3.0
    v_cbam[v_cbam < -3.0] = -3.0
    cbam_eff = Price_model.second_order_dprice(v_cbam, direct_impact="passthrough")
    dp_cbam = cbam_eff['dp_full']
    v_cbam = cbam_eff['v_calculated']

    # DYNAMIC['cbam_cost_intermediates'] = cbam_incidence[~cbam_incidence['PROD_COMM'].str.contains("FD")].group_by([''])
    # cbam_price = BTA_cou.calc_cbam_direct_v(DYNAMIC['cbam_incidence'][year], MRIO_vec_to_df_DEF(DYNAMIC['output'][year-1],'q'))
    # v_cbam = MRIO_df_to_vec_DEF(cbam_price, 'delta_cbam_weight')

    v_dev_normal_output[v_dev_normal_output < -0.5] = -0.5
    v_dev_profit_rate[v_dev_profit_rate < -0.5] = -0.5
    v_output_growth[v_output_growth < -0.5] = -0.5
    v_scarcity_rent[v_scarcity_rent < 0] = 0.0
    v_labor[v_labor < -0.5] = -0.5

    # v_all = v_labor + v_tax + v_dev_normal_output + v_exog
    v_all = v_exog + v_ctax + v_dev_normal_output + v_labor + v_dev_profit_rate + v_output_growth + v_cbam + v_scarcity_rent
    v_wo_cbam = v_all - v_cbam

    dp_pre_trade = Price_model.second_order_dprice(v_all)['dp_full']
    self.V.write_var("v_all", year, v_all)

    dp_no_cbam = Price_model.second_order_dprice(v_wo_cbam)['dp_full']
    
    price_change_pre_trade = Price_model.calc_dp_pre_trade_bta(
        MRIO_vec_to_df_DEF(dp_no_cbam,'delta_p').rename(columns={'PROD_COMM':'TRAD_COMM','REG_imp':'REG_exp'}),
        cbam_cost_dfs['intermediates'], ind_energy, self.V.read_var('price_index', year-1, as_df=True))

    print("--- 2.2.7 Production cost and price: %s seconds ---" % round(time.time() - module_time, 1))
    #endregion

    #region 2.2.08_Household_impacts [rgba(52,152,219,0.1)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.8] Household impacts calculation
    # ^w        get baseline HH consumption (already increased in [2.1]), add HH_price and recyc_rev impacts
    # ^w        then consider the growth effect 
    #endregion
    module_time = time.time()

    # Construct household model
    HH_model = hh(EXOG_VARS)
    if year != self.model_start:
        # ^b [DYNAMICS]: update HH consumption
        HH_model.HH = self.V.read_var('household_consumption', year-1, as_df=True).rename(columns={'household_consumption':'VIPA'}).set_index(['REG_imp','REG_exp','TRAD_COMM'])

    HH_model.load_dynamic({
        'wage_base': self.V.read_var('wage', year, as_df=True),
        'employment_base': self.V.read_var("employment_base", year, as_df=True),
        'cpi': self.V.read_var('cpi', year-1, as_df=True),
        'save_rate1': self.V.read_var('save_rate', year-1, as_df=True),
        'save_rate2': self.V.read_var('save_rate', year-2, as_df=True),
        'save_rate3': self.V.read_var('save_rate', year-3, as_df=True),
        'hh_exog': Scenario.hh_exog
    })

    if year > self.model_start:
        HH_price = HH_model.build_hh_price(price_change_pre_trade, emission_cost_dfs['hh'], self.V.read_var('price_index', year-1, as_df=True), prev=self.V.read_var_df('emission_cost_hh', year-1), year=year)
    else:
        HH_price = HH_model.build_hh_price(price_change_pre_trade, emission_cost_dfs['hh'], self.V.read_var('price_index', year-1, as_df=True))
    # TODO this is a biggie: we need to make sure that all DATA complies to a given set of typing
    # TODO TRAD_COMM should be int16; PROD_COMM str; REG_exp and REG_imp str
    HH_price = HH_price.astype({'TRAD_COMM':'int'})

    # add growth effect (income) is year > year[0]
    HH_price_eff, HH_inc_eff, HH_save_eff = HH_model.calc_hh_demand_change(HH_price, recyc_rev_base, Scenario.inc_exog, self.V.read_var('inc_exog', year-1, as_df=True).rename(columns={'inc_exog':'dlabor_exog'}), year=year)
    if year > self.model_start:
        if year == self.years[1]:
            HH_tech_substitution = Energy_emissions.hh_fuel_substitution(ener_base, self.V.read_var('household_consumption', year-1, as_df=True).rename(columns={'household_consumption':'VIPA'}).set_index(['REG_imp','REG_exp','TRAD_COMM']), self.V.read_var('household_consumption', year-1, as_df=True).rename(columns={'household_consumption':'VIPA'}).set_index(['REG_imp','REG_exp','TRAD_COMM']), DYNAMIC['HH_price'][year-1])
        if year > self.years[1]:
            HH_tech_substitution = Energy_emissions.hh_fuel_substitution(ener_base, self.V.read_var('household_consumption', year-1, as_df=True).rename(columns={'household_consumption':'VIPA'}).set_index(['REG_imp','REG_exp','TRAD_COMM']), self.V.read_var('household_consumption', year-2, as_df=True).rename(columns={'household_consumption':'VIPA'}).set_index(['REG_imp','REG_exp','TRAD_COMM']), DYNAMIC['HH_price'][year-1])
    else:
        HH_tech_substitution = pd.DataFrame(columns=['REG_imp','REG_exp','TRAD_COMM','VIPA_imp'])
    
    dy_hh_price = IO_model.build_dy_hh(HH_price_eff, 'delta_y_price')
    dy_hh_inc = IO_model.build_dy_hh(HH_inc_eff, 'delta_y_inc')
    dy_hh_save = IO_model.build_dy_hh(HH_save_eff, 'delta_y_save')
    dy_hh_tech_substitution = IO_model.build_dy_hh(HH_tech_substitution, 'VIPA_imp')

    if calibration_counter == 0:
        dy_calibration_residual = np.zeros_like(dy_hh_inc)
    else:
        hh_fd = MRIO_df_to_vec(CALIBRATION_VARS['residual_fd_hh'].reset_index(), 'REG_exp', 'TRAD_COMM', 'VIPA',EXOG_VARS.R_list, EXOG_VARS.P_list)
        gov_fd = MRIO_df_to_vec(CALIBRATION_VARS['residual_fd_gov'].reset_index(), 'REG_exp', 'TRAD_COMM', 'VIGA',
                                           EXOG_VARS.R_list, EXOG_VARS.P_list)
        fcf_fd = MRIO_df_to_vec(CALIBRATION_VARS['residual_fd_fcf'].reset_index(), 'REG_exp', 'TRAD_COMM', 'VDFA',
                                           EXOG_VARS.R_list, EXOG_VARS.P_list)
        dy_calibration_residual = hh_fd + gov_fd + fcf_fd

    print("--- 2.2.8 Household module: %s seconds ---" % round(time.time() - module_time, 1))

    #endregion

    #region 2.2.09_Government [rgba(52,152,219,0.1)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.9] Government calculations
    # ^w        mostly revenue recycling 
    #endregion

    module_time = time.time()
    # Construct government model
    GOV_model = gov(EXOG_VARS, Scenario)

    GOV_model.calc_trade_share()
    GOV_recyc = GOV_model.calc_gov_demand_change(recyc_rev_base, self.V.read_var('price_index', year-1))
    
    dy_gov_recyc = MRIO_df_to_vec(GOV_recyc.reset_index(), 'REG_exp', 'TRAD_COMM', 'delta_y_gov', EXOG_VARS.R_list, EXOG_VARS.P_list)

    if recyc_rev_base['recyc_govt_base'].sum() != dy_gov_recyc.sum():
        ratio = dy_gov_recyc.sum() / recyc_rev_base['recyc_govt_base'].sum()
        print("#############")
        print("### WARNING: government expenditures [dy_gov_recyc] from recycling are not fully spent; only {:.0%} is spent".format(ratio))
        print("#############")

    if year > self.model_start:
        dy_gov_delta = MRIO_df_to_vec(DYNAMIC['govt_spending_delta'].reset_index(), 'REG_exp', 'TRAD_COMM', 'VIGA', EXOG_VARS.R_list, EXOG_VARS.P_list)
    else:
        dy_gov_delta = np.zeros_like(dy_gov_recyc)

    print("--- 2.2.9 Government module: %s seconds ---" % round(time.time() - module_time, 1))
    #endregion

    #region 2.2.10_Trade [rgba(52,152,219,0.2)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.10] Trade calculations
    # ^w        re-calculating IO table based on price effects in trade, unless it doesn't really do that
    # ^w
    # TODO  it only recalculates the A matrix, not the rest of the tables (Leontief, Ghosh) after trade
    #endregion

    module_time = time.time()
    # Construct trade model
    Trade_model = trade(EXOG_VARS)
    Trade_model.load_dynamic({
        'va_prev1' : DYNAMIC['value_added'][year-1],
        'va_prev2' : DYNAMIC['value_added'][year-2],
        'va_prev3' : DYNAMIC['value_added'][year-3],
        'price_index': self.V.read_var('price_index', year-1, as_df=True),
        'price_index_prev': self.V.read_var('price_index', year-2, as_df=True)
    })
    Trade_model.calculate_dynamics()
    ind_trade = Trade_model.calc_IO_coef(ind_ener_glo, price_change_pre_trade, year)

    # calculate FD substitution
    fd_trade_response = Trade_model.calc_FD_substitution(price_change_pre_trade)
    dy_trade_hh = fd_trade_response['dy']['dy_trade_hh']
    dy_trade_fcf = fd_trade_response['dy']['dy_trade_fcf']
    dy_trade_gov = fd_trade_response['dy']['dy_trade_gov']
    
    # Build new A matrix due to trade (import) substitution
    A_trade = IO_model.build_A_matrix(input_df=ind_trade, variable='IO_coef_trade')
    # ! UPDATE Leontieff after trade
    IO_model.update_Leontieff(A_trade)
    dq_trade_eff = IO_model.calc_dq_trade((dq_tech_eff))
    self.V.write_var("dq_trade_eff", year, dq_trade_eff)

    Price_model.update_A_BASE(A_trade)
    Price_model.calc_positive_and_negative_L()

    # Calculate output changes for each driver of output change
    trade_dy = dy_trade_hh + dy_trade_fcf + dy_trade_gov

    # then calculate HH impacts of trade
    dq_trade_hh = IO_model.calc_dq_exog(dy_trade_hh)
    dq_trade_fcf = IO_model.calc_dq_exog(dy_trade_fcf)
    dq_trade_gov = IO_model.calc_dq_exog(dy_trade_gov)
    self.V.write_var("dq_trade_hh", year, dq_trade_hh)
    self.V.write_var("dq_trade_fcf", year, dq_trade_fcf)
    self.V.write_var("dq_trade_gov", year, dq_trade_gov)
    

    dq_hh_price, dq_hh_inc, dq_hh_save = IO_model.calc_dq_hh(dy_hh_price, dy_hh_inc, dy_hh_save)
    self.V.write_var("dq_hh_price", year, dq_hh_price)
    self.V.write_var("dq_hh_inc", year, dq_hh_inc)
    self.V.write_var("dq_hh_save", year, dq_hh_save)

    dq_hh_tech_substitution = IO_model.calc_dq_exog(dy_hh_tech_substitution)
    dq_calibration_residual = IO_model.calc_dq_exog(dy_calibration_residual)

    dq_gov_delta = IO_model.calc_dq_exog(dy_gov_delta)
    dq_gov_recyc = IO_model.calc_dq_gov(dy_gov_recyc)
    self.V.write_var("dq_gov_delta", year, dq_gov_delta)
    self.V.write_var("dq_gov_recyc", year, dq_gov_recyc)

    # Calculate price changes
    dp_all = Price_model.second_order_dprice(self.V.read_var('v_all', year))['dp_full']
    self.V.write_var("dp_all", year, dp_all)

    print("--- 2.2.10 Trade module: %s seconds ---" % round(time.time() - module_time, 1))

    #endregion

    #region 2.2.11_Exog_demand_&_growth [rgba(52,152,219,0.1)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.11] Exogenous demand and growth
    # ^w        second, calculate dq of exogenous demand effects
    #endregion

    module_time = time.time()

    # ! add in exog FD

    dy_hh_exog_fd = MRIO_df_to_vec(Scenario.fd_exog.query("PROD_COMM == 'FD_1'"), 
                                                        'REG_exp', 'TRAD_COMM', 'dy', 
                                                        EXOG_VARS.R['Region_acronyms'].to_list(), EXOG_VARS.P['Lfd_Nr'].to_list())
    dq_hh_exog_fd = IO_model.calc_dq_exog(dy_hh_exog_fd)
    DYNAMIC['dq_exog_hh_prev'] = dq_hh_exog_fd

    dy_hh_exog = MRIO_df_to_vec(Scenario.hh_exog, 
                                                        'REG_exp', 'TRAD_COMM', 'dy', 
                                                        EXOG_VARS.R['Region_acronyms'].to_list(), EXOG_VARS.P['Lfd_Nr'].to_list())
    self.V.write_var('dy_hh_exog', year, dy_hh_exog)
    dq_hh_exog = IO_model.calc_dq_exog(dy_hh_exog)

    dy_gov_exog_fd = MRIO_df_to_vec(Scenario.fd_exog.query("PROD_COMM == 'FD_3'"), 
                                                        'REG_exp', 'TRAD_COMM', 'dy', 
                                                        EXOG_VARS.R['Region_acronyms'].to_list(), EXOG_VARS.P['Lfd_Nr'].to_list())
    dq_gov_exog_fd = IO_model.calc_dq_exog(dy_gov_exog_fd)
    DYNAMIC['dq_exog_gov_prev'] = dq_gov_exog_fd
    
    dy_fcf_exog_fd = MRIO_df_to_vec(Scenario.fd_exog.query("PROD_COMM == 'FD_4'"), 
                                                        'REG_exp', 'TRAD_COMM', 'dy', 
                                                        EXOG_VARS.R['Region_acronyms'].to_list(), EXOG_VARS.P['Lfd_Nr'].to_list())
    dq_fcf_exog_fd = IO_model.calc_dq_exog(dy_fcf_exog_fd)
    DYNAMIC['dq_exog_fcf_prev'] = dq_fcf_exog_fd

    print("--- 2.2.11 Exogenous demand: %s seconds ---" % round(time.time() - module_time, 1))

    #endregion

    #region 2.2.12_Supply_constraint [rgba(52,152,219,0.2)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.12] Supply constraint
    # ^w        supply constraint is a Ghoshian-inverse supply effect, with criticality modifiers
    # ^w        
    # TODO  there is a lot to do here, currently it does NOT restrict supply, only decreases it
    #endregion

    module_time = time.time()

    # Introduce supply constraints
    supply_constraint = IO_model.calc_dq_supply_constraint3(Scenario.supply_constraint)
    dq_supply_constraint = supply_constraint['dq_supply_constraint']
    # ! FEEDBACK from supply constraint to consumption is missing
    # ! i.e. y0 is not changing as it should 
    # TODO y0 is not changing

    supply_constraint_no_empl = IO_model.calc_dq_supply_constraint(Scenario.supply_constraint_no_empl_change)
    dq_supply_constraint_no_empl = supply_constraint_no_empl['dq_supply_constraint']

    print("--- 2.2.12 Supply constraints: %s seconds ---" % round(time.time() - module_time, 1))

    #endregion

    #region 2.2.13_Investment [rgba(52,152,219,0.1)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.13] Investment calculation
    # ^w        investment demand is channeled through the investment converter, which leads to new demand
    # ^w        
    # TODO  not working with updated Leontieff!!
    #endregion

    module_time = time.time()

    INV_CONV = Scenario.set_inv_conv_adj(DYNAMIC['investment_converter']) #type:ignore

    # Construct investment model
    INV_model = invest(EXOG_VARS, INV_CONV, Scenario, year)
    INV_model.load_dynamic({
        'dk_base': self.V.read_var('dk_base', year, as_df=True)
    })

    INV_model.calc_inv_share()

    # Calculate new final demand due to investment
    INV_model.calc_dy_inv_recyc(recyc_rev_base, self.V.read_var('price_index', year-1))
    INV_model.calc_dy_inv_exog(Scenario.inv_exog)

    # ! chcke if government investment uses 100% of recycled amount
    dy_inv_recyc = MRIO_df_to_vec(INV_model.dy_inv_recyc,"REG_exp", "TRAD_COMM",
                                "dy", EXOG_VARS.R['Region_acronyms'].to_list(), EXOG_VARS.P['Lfd_Nr'].to_list())
    if recyc_rev_base['recyc_inv_base'].sum() != dy_inv_recyc.sum():
        ratio = dy_inv_recyc.sum() / recyc_rev_base['recyc_inv_base'].sum()
        print("#############")
        print("### WARNING: government investments [dy_inv_recyc] from recycling are not fully spent; only {:.0%} is spent".format(ratio))
        print("#############")

    dy_inv_exog = MRIO_df_to_vec(INV_model.dy_inv_exog, "REG_exp", "TRAD_COMM",
                                "dy", EXOG_VARS.R['Region_acronyms'].to_list(), EXOG_VARS.P['Lfd_Nr'].to_list())


    # Remove electricity investment from lagged investment so there is no double counting
    if self.ftt_run:
        n_sectors = len(INV_model.P_list)  # 120
        elec_idx = np.arange(92, len(INV_model.R_list) * n_sectors, n_sectors)
        DYNAMIC['dy_inv_induced_L1'][elec_idx] = 0
    dq_inv_induced, dq_inv_recyc, dq_inv_exog = IO_model.calc_dq_inv(DYNAMIC['dy_inv_induced_L1'], dy_inv_recyc, dy_inv_exog)
    self.V.write_var("dq_inv_exog", year, dq_inv_exog)
    self.V.write_var("dq_inv_recyc", year, dq_inv_recyc)
    self.V.write_var("dq_inv_induced", year, dq_inv_induced)

    print("--- 2.2.13 Investment module: %s seconds ---" % round(time.time() - module_time, 1))

    #endregion

    #region 2.2.14_Employment [rgba(52,152,219,0.2)]
    #region desc [rgba(52,152,219,0.6)]
    # ^w    [2.2.14] Employment calculation
    # ^w        investment demand is channeled through the investment converter, which leads to new demand
    # ^w        
    # TODO  still need to check dynamics / re-calculation
    #endregion

    module_time = time.time()
    # Empl_model = empl(EXOG_VARS)

    # if year == self.model_start:
    #     employment_base = Empl_model.calc_initial()
    #     self.V.write_var("employment_base", year, employment_base, from_df=True)

    Empl_model.load_dynamic({
        'q_base':self.V.read_var("output", year-1),
        'k':self.V.read_var('k', year),
        'k1':self.V.read_var('k', year-1),
        'empl_base':self.V.read_var('employment_base', year),
        'wage': self.V.read_var('wage', year, as_df=True) if year > self.model_start else None,
        'wage_prev1': self.V.read_var('wage', year-1, as_df=True) if year > self.model_start else None,
        'cpi': self.V.read_var('cpi', year-1, as_df=True) if year > self.model_start else None,
        'cpi_prev1': self.V.read_var('cpi', year-2, as_df=True) if year > self.model_start else None
    })

    Cost_curves = cost_curves(EXOG_VARS)

    if year == self.model_start:
        pass
    else:
        Cost_curves.load_dynamic({
            'q_base': self.V.read_var("output", self.model_start, as_df=True),
            'q_current': self.V.read_var("output", year-1, as_df=True),
            'q_prev': self.V.read_var("output", year-2, as_df=True),
            'empty_io': self.V.retrieve_empty_table('energy_flows')
        })
        cost_curves_impact = Cost_curves.calc_cost_impact()
        cost_curves_io = Cost_curves.build_io_change(cost_curves_impact)

    # Build employment model
    if year == self.model_start:
        # Empl_model.build_empl_coef()
        # Empl_model.calc_empl_multiplier(MRIO_df_to_vec(Prod_cost.empl_base,"REG_imp","PROD_COMM","vol_total",EXOG_VARS.R['Region_acronyms'].to_list(),EXOG_VARS.P['Lfd_Nr'].to_list()), IO_model.q_base)
        # dq_IO_eff is just here for its dimensions, no particular reason other than that
        dempl_productivity = np.zeros_like(dq_hh_price)
        dempl_costcurve = np.zeros_like(dq_hh_price)
    else:
        # if productivity changes; dempl adjusts automatically, but also need to adjust base empl
        # REG_imp | PROD_COMM | vol_total
        # empl_new = MRIO_vec_to_df_DEF(Empl_model.recalc_empl_base(IO_model.q_base), 'vol_total')
        # empl_new = empl_new.merge(Prod_cost.empl_base.rename(columns={'vol_total':'vol_base'}), how='left', on=['REG_imp','PROD_COMM'])
        empl_new = Empl_model.recalc_empl_base_NEW()
        dempl_productivity = empl_new['d_employment']   
        # ! this has an effect on compensation!!! 
        dlabor_productivity = MRIO_vec_to_df_DEF(empl_new['d_labor'], 'dlabor_prod')

        empl_costcurve = Empl_model.calc_dempl_perc(MRIO_df_to_vec_DEF(cost_curves_impact, "input_cost_change"))
        dempl_costcurve = empl_costcurve['d_employment']
        dlabor_costcurve = MRIO_vec_to_df_DEF(empl_costcurve['d_labor'], 'dlabor_costcurve')

    # Calculate employment changes due to output changes
    dq_total_empl = (dq_trade_eff + dq_tech_eff + dq_hh_price + dq_hh_inc + dq_hh_save + dq_hh_exog + dq_gov_recyc + dq_gov_delta + dq_calibration_residual + 
                dq_inv_induced + dq_inv_recyc + dq_inv_exog + dq_hh_exog_fd + dq_fcf_exog_fd + dq_gov_exog_fd + dq_supply_constraint +  
                dq_structural_change_wo_employment + dq_hh_tech_substitution)

    dq_total = (dq_trade_eff + dq_tech_eff + dq_hh_price + dq_hh_inc + dq_hh_save + dq_hh_exog + dq_gov_recyc + dq_gov_delta + dq_calibration_residual + 
                dq_inv_induced + dq_inv_recyc + dq_inv_exog + dq_hh_exog_fd + dq_fcf_exog_fd + dq_gov_exog_fd + dq_supply_constraint +  
                dq_structural_change + dq_supply_constraint_no_empl + dq_hh_tech_substitution)
    self.V.write_var("dq_total", year, dq_total)

    dempl = Empl_model.calc_dempl({
        'total':                dq_total_empl,
        'tech_eff':             dq_tech_eff,
        'trade_eff':            dq_trade_eff,
        'trade_hh':             dq_trade_hh,
        'trade_gov':            dq_trade_gov,
        'trade_fcf':            dq_trade_fcf,
        'hh_price':             dq_hh_price,
        'hh_inc':               dq_hh_inc,
        'hh_save':              dq_hh_save,
        'hh_exog':              dq_hh_exog,
        'gov_recyc':            dq_gov_recyc,
        'gov_delta':            dq_gov_delta,
        'inv_induced':          dq_inv_induced,
        'inv_recyc':            dq_inv_recyc,
        'inv_exog':             dq_inv_exog,
        'hh_exog_fd':           dq_hh_exog_fd,
        'fcf_exog_fd':          dq_fcf_exog_fd,
        'gov_exog_fd':          dq_gov_exog_fd,
        'supply_constraint':    dq_supply_constraint,
        'calibration_residual': dq_calibration_residual,
        'structural_change':    dq_structural_change_wo_employment,
        'hh_tech_substitution': dq_hh_tech_substitution,
    })
    dempl_total               = dempl['total']
    dempl_tech_eff            = dempl['tech_eff']
    dempl_trade_eff           = dempl['trade_eff']
    dempl_trade_hh            = dempl['trade_hh']
    dempl_trade_gov           = dempl['trade_gov']
    dempl_trade_fcf           = dempl['trade_fcf']
    dempl_hh_price            = dempl['hh_price']
    dempl_hh_inc              = dempl['hh_inc']
    dempl_hh_save             = dempl['hh_save']
    dempl_hh_exog             = dempl['hh_exog']
    dempl_gov_recyc           = dempl['gov_recyc']
    dempl_gov_delta           = dempl['gov_delta']
    dempl_inv_induced         = dempl['inv_induced']
    dempl_inv_recyc           = dempl['inv_recyc']
    dempl_inv_exog            = dempl['inv_exog']
    dempl_hh_exog_fd          = dempl['hh_exog_fd']
    dempl_fcf_exog_fd         = dempl['fcf_exog_fd']
    dempl_gov_exog_fd         = dempl['gov_exog_fd']
    dempl_supply_constraint   = dempl['supply_constraint']
    dempl_calibration_residual = dempl['calibration_residual']
    dempl_structural_change   = dempl['structural_change']
    dempl_hh_tech_substitution = dempl['hh_tech_substitution']
    
    # ! need to add productivity change induced; NOTE: it does NOT have direct output impacts
    dempl_total = dempl_total + dempl_productivity

    print("--- 2.2.14 Employment module: %s seconds ---" % round(time.time() - module_time, 1))

    # ! need to account for labour supply constraint, we set it as == UNEMP min 2% of LF
    # employment_constraint = Empl_model.calc_dempl_constraint(
        # self.V.read_var("employment_base", year),
        # dempl_total+dempl_productivity+dempl_costcurve,
        # np.zeros_like(dempl_total),
        # self.V.read_var("output", year-1),
        # dq_total,
        # DYNAMIC['labour_force'][year],
        # self.V.read_var("shadow_nat_employment", year-1, as_df=True),
        # year
    # )
    # dempl_labour_supply_constraint = employment_constraint['dL']
    # empl_labour_supply_constraint = IO_model.calc_dq_supply_constraint2(employment_constraint['dQ'], dq_total)
    # dq_empl_labour_supply_constraint = empl_labour_supply_constraint['dq']

    # ! need to adjust consumption as well
    # dy_empl_labour_supply_constraint = empl_labour_supply_constraint['dy']

    # dq_total = dq_total + dq_empl_labour_supply_constraint
    # dempl_total = dempl_total + dempl_labour_supply_constraint

    #endregion

    dq_total_iter = pd.concat([EXOG_VARS.mrio_id, pd.DataFrame(
        dq_total, columns = ["dq_0"])], axis=1)
    dempl_total_iter = pd.concat([EXOG_VARS.mrio_id, pd.DataFrame(
        dempl_total, columns = ["dempl_0"])], axis=1)
    dlabor_iter = pd.concat([EXOG_VARS.mrio_id, pd.DataFrame(
        np.zeros(dq_total.shape), columns = ["dlabor_0"])], axis=1)


    #%%
    labor_cond_ssq_prev = np.inf
    labor_cond_ssq = np.inf

    #region 2.2.15_Within_year_iteration [rgba(26,188,156,0.10)] 
    #region desc [rgba(26,188,156,0.50)] 
    # ^w    [2.2.15] WITHIN YEAR ITERATION LOOP 
    # ^w        process for within year iteration:
    # ^w        (1) set income to be based on new Prod_cost (labour compensation) + dlabor
    # ^w        (2) recalculate prices
    # ^w        (3) recalculate most stuff based on these changes
    #endregion

    # Iter_comment:
    # Here we change labor income by using the % change in employment
    # abs_change_employment / empl_base * labor_expenditure      


    iter_run, hh_approx = 1, 0
    dtax_rev, dlabor_nat = None, None
    A_trade_old = None
    cost_curves_impact_old = None
    dempl_labour_supply_constraint = np.zeros_like(dempl_total)
    # these are the thereshold values for convergence
    # labor_diff, tax_diff = 0.05, 0.05
    # A_trade_diff = 0.05
    # absolute price change difference between iterations (this is in percentage, i.e. 0.01 -> 1%)
    # price_diff = 0.05

    dp_all_wo_iter = dp_all.copy()

    while self.SWITCH_WITHIN_YEAR_LOOP:
        iter_time = time.time()

        #region 2.2.15.1_Adjust_labour_income [rgba(26,188,156,0.15)]
        #region desc [rgba(26,188,156,0.50)]
        # ^w    [2.2.15.1] Labour income adjustment
        # ^w        calculate delta tax revenue and take dempl_total, calculate new labour compensation based on those
        #endregion
        A_old = A_trade
        dp_all_old = dp_all
        v_costcurve_old = v_costcurve.copy() if iter_run > 1 else np.zeros_like(dp_all)
        emission_cost_old = emission_cost_dfs['intermediates'] if iter_run == 1 else self.V.read_var_df('emission_cost_intermediates', year)

        dq_hh_inc_old = dq_hh_inc.copy()
        dq_hh_price_old = dq_hh_price.copy()
        dq_hh_save_old = dq_hh_save.copy()
        dq_total_old = dq_total.copy()

        if year > self.model_start:
            cost_curves_impact_old = cost_curves_impact[['REG_imp','PROD_COMM','input_cost_change']].copy()
            cost_curves_impact_old = cost_curves_impact_old.rename(columns={'input_cost_change':'input_cost_change_old'})

        if iter_run > 1:
            dempl_labour_supply_constraint = np.zeros_like(dempl_total)

        # ? calculate new emission cost based on new trade and new output
        Energy_emissions.update_ind_base(A_trade, self.V.read_var("output", year-1) + self.V.read_var("dq_total", year))
        tax_incidence = Energy_emissions.calculate_tax_incidence()
        self.V.write_var_df('emission_cost_intermediates', year, tax_incidence['tax_incidence_intermediates'])
        self.V.write_var_df('emission_cost_hh',  year, tax_incidence['tax_incidence_hh'].rename(columns={'PROD_COMM': 'FD'}))
        self.V.write_var_df('emission_cost_fcf', year, tax_incidence['tax_incidence_fcf'].rename(columns={'PROD_COMM': 'FD'}))
        self.V.write_var_df('emission_cost_gov', year, tax_incidence['tax_incidence_gov'].rename(columns={'PROD_COMM': 'FD'}))

        cbam_incidence = BTA_cou.calc_cbam_incidence(ind_ener_glo, DYNAMIC['carbon_content'], EXOG_VARS.HH_BASE, EXOG_VARS.FCF_BASE, EXOG_VARS.GOV_BASE)
        # cbam incidence ['REG_imp','REG_exp','PROD_COMM','TRAD_COMM','cbam_cost']
        _cbam_interm = cbam_incidence[~cbam_incidence['PROD_COMM'].str.contains("FD")].copy()
        _cbam_interm = _cbam_interm.astype({'PROD_COMM': int, 'TRAD_COMM': int})
        self.V.write_var_df('cbam_cost_intermediates', year, _cbam_interm)
        self.V.write_var_df('cbam_cost_hh',  year, cbam_incidence[cbam_incidence['PROD_COMM']=="FD_1"].rename(columns={'PROD_COMM':'FD'}))
        self.V.write_var_df('cbam_cost_fcf', year, cbam_incidence[cbam_incidence['PROD_COMM']=="FD_4"].rename(columns={'PROD_COMM':'FD'}))
        self.V.write_var_df('cbam_cost_gov', year, cbam_incidence[cbam_incidence['PROD_COMM']=="FD_3"].rename(columns={'PROD_COMM':'FD'}))

        # calculate within iteration delta of collected tax revenues
        dtax_rev = Tax_rev.calc_tax_iter_cond(emission_cost_old, self.V.read_var_df('emission_cost_intermediates', year))

        # ? calculate cost curve sector changes
        if year > self.model_start:
            cost_curves_impact = Cost_curves.calc_cost_impact(dq=dq_total)
            cost_curves_impact = cost_curves_impact.merge(cost_curves_impact_old, how='left', on=['REG_imp','PROD_COMM']).fillna(0)

            dampening_factor = {
                1: 0.9,
                5: 0.75,
                10: 0.5,
                20: 0.3,
                30: 0.2,
                40: 0.1
            }
            if iter_run in dampening_factor.keys():
                omega = dampening_factor[iter_run]

            overshot = np.sign(cost_curves_impact['input_cost_change']) != np.sign(cost_curves_impact['input_cost_change_old'])

            cost_curves_impact['input_cost_change'] = np.where(
                overshot,
                (cost_curves_impact['input_cost_change'] + cost_curves_impact['input_cost_change_old']) / 2,
                (1 - omega) * cost_curves_impact['input_cost_change'] + omega * cost_curves_impact['input_cost_change_old'],
            )
            cost_curves_io = Cost_curves.build_io_change(cost_curves_impact)
            empl_costcurve = Empl_model.calc_dempl_perc(MRIO_df_to_vec_DEF(cost_curves_impact, "input_cost_change"))
            # dempl_costcurve = empl_costcurve['d_employment']
            dlabor_costcurve = MRIO_vec_to_df_DEF(empl_costcurve['d_labor'], 'dlabor_costcurve')
        
        # calculate output based on current dq_total
        # output = Inc_model.calc_output(dq_total)
        # calculate energy flows and taxes
        # ind_ener_cou = Inc_model.collect_ener_flow(ind_trade, None, tax_rate)
        # ? tax_rev_cou_base = Tax_rev.calc_tax_rev_base(tax_rate)
        
        # Tax revenue after changes in household demand
        # ind_ener_hh = Inc_model.collect_ener_flow_hh(HH_model, None, tax_rate_hh)
        # ? tax_rev_hh_base = Tax_rev.calc_tax_rev_hh_base(tax_rate_hh)
        
        # calculate new labour comepnsation based on dempl_total (wages are constant)
        dlabor_sec = Inc_model.calc_labor_comp_change(dempl_total+dempl_labour_supply_constraint)
        # ! NOMINAL change in compensation!

        if year > self.model_start:
            # ! total employment with new wage
            g_labor_comp = Inc_model.recalc_labor_comp_delta() # labor comp is always nominal
            dlabor_sec = dlabor_sec.merge(g_labor_comp, how='left', on=['REG_imp','PROD_COMM'])
            dlabor_sec = dlabor_sec.merge(dlabor_productivity, how='left', on=['REG_imp','PROD_COMM'])
            dlabor_sec = dlabor_sec.merge(dlabor_costcurve, how='left', on=['REG_imp','PROD_COMM'])
            dlabor_sec['dlabor'] = dlabor_sec['dlabor'] + dlabor_sec['glabor'] + dlabor_sec['dlabor_prod'] + dlabor_sec['dlabor_costcurve']
            dlabor_sec = dlabor_sec.drop(columns=['glabor','dlabor_prod','dlabor_costcurve'])

        dlabor_nat = Inc_model.calc_labor_iter_cond(dlabor_sec, dlabor_nat)
        dlabor_sec.columns = ["REG_imp", "PROD_COMM", f"dlabor_{iter_run}"]

        #endregion

        #region 2.2.15.2_Adjust_prices [rgba(26,188,156,0.20)] 
        #region desc [rgba(26,188,156,0.50)] 
        # ^w    [2.2.15.2] Price adjustment 
        # ^w        prices changes are calculated based on dtax changes, new prod cost is fed in to prices
        # ^w        NO new technology substitution calculation
        # ^w
        # TODO      no recalculation of L and G matrices
        #endregion

        tax_rev_interm = self.V.read_var_df('emission_cost_intermediates', year).groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev'})
        tax_rev_hh = self.V.read_var_df('emission_cost_hh', year).groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev_hh'})
        tax_rev_fcf = self.V.read_var_df('emission_cost_fcf', year).groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev_fcf'})
        tax_rev_gov = self.V.read_var_df('emission_cost_gov', year).groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev_gov'})

        cbam_interm = self.V.read_var_df('cbam_cost_intermediates', year).groupby(['REG_imp']).agg({'cbam_cost':'sum'}).reset_index().rename(columns={'cbam_cost':'cbam_rev'})
        cbam_hh =  self.V.read_var_df('cbam_cost_hh', year).groupby(['REG_imp']).agg({'cbam_cost':'sum'}).reset_index().rename(columns={'cbam_cost':'cbam_rev_hh'})
        cbam_fcf = self.V.read_var_df('cbam_cost_fcf', year).groupby(['REG_imp']).agg({'cbam_cost':'sum'}).reset_index().rename(columns={'cbam_cost':'cbam_rev_fcf'})
        cbam_gov =  self.V.read_var_df('cbam_cost_gov', year).groupby(['REG_imp']).agg({'cbam_cost':'sum'}).reset_index().rename(columns={'cbam_cost':'cbam_rev_gov'})

        tax_rev = tax_rev_interm.merge(tax_rev_hh, how='outer', on=['REG_imp']).merge(tax_rev_fcf, how='outer', on='REG_imp').merge(tax_rev_gov, how='outer', on='REG_imp')
        tax_rev = tax_rev.merge(cbam_interm, how='outer', on=['REG_imp']).merge(cbam_hh, how='outer', on='REG_imp').merge(cbam_fcf, how='outer', on='REG_imp')
        tax_rev = tax_rev.merge(cbam_gov, how='outer', on='REG_imp')
        tax_rev = tax_rev.fillna(0)
        tax_rev['tax_rev'] = tax_rev['tax_rev'] + tax_rev['tax_rev_hh'] + tax_rev['tax_rev_fcf'] + tax_rev['tax_rev_gov']
        tax_rev['tax_rev'] = tax_rev['tax_rev'] + tax_rev['cbam_rev'] + tax_rev['cbam_rev_hh'] + tax_rev['cbam_rev_fcf'] + tax_rev['cbam_rev_gov'] 
        tax_rev = tax_rev[['REG_imp','tax_rev']].copy()

        if year > self.model_start:
            recyc_rev_base = Tax_rev.calc_recyc_rev(tax_rev, rev_split)
            DYNAMIC['carbon_tax_revenues'][year] = recyc_rev_base.copy()
            recyc_rev_base = Tax_rev.subtract_prev(recyc_rev_base, DYNAMIC['carbon_tax_revenues'][year-1])
        else:
            recyc_rev_base = Tax_rev.calc_recyc_rev(tax_rev, rev_split)
            DYNAMIC['carbon_tax_revenues'][year] = recyc_rev_base.copy()
        
        #? dtax_rev = Tax_rev.calc_tax_iter_cond(tax_rev, dtax_rev)

        # ! carbon price
        if year == self.model_start:
            emission_cost = self.V.read_var_df('emission_cost_intermediates', year).groupby(['REG_imp','PROD_COMM']).agg({'emission_cost':'sum'}).reset_index()
        else:
            emission_cost = self.V.read_var_df('emission_cost_intermediates', year).groupby(['REG_imp','PROD_COMM']).agg({'emission_cost':'sum'}).reset_index()
            emission_cost_prev = self.V.read_var_df('emission_cost_intermediates', year-1).groupby(['REG_imp','PROD_COMM']).agg({'emission_cost':'sum'}).reset_index()
            emission_cost = emission_cost.merge(emission_cost_prev.rename(columns={'emission_cost':'prev'}), how='outer').fillna(0)
            emission_cost['emission_cost'] = emission_cost['emission_cost'] - emission_cost['prev']
            emission_cost = emission_cost.drop(columns=['prev'])
        v_ctax = Prod_cost.calc_prod_cost_impact(MRIO_df_to_vec_DEF(emission_cost, 'emission_cost'))
        # ! limit ctax to 300% price increase
        v_ctax[v_ctax > 3.0] = 3.0
        ctax_effect = Price_model.second_order_dprice(v_ctax, direct_impact="passthrough")
        dp_ctax = ctax_effect['dp_full']
        v_ctax = ctax_effect['v_calculated']

        if year == self.model_start:
            cbam_cost = self.V.read_var_df('cbam_cost_intermediates', year).groupby(['REG_imp','PROD_COMM']).agg({'cbam_cost':'sum'}).reset_index()
        else:
            cbam_cost = self.V.read_var_df('cbam_cost_intermediates', year).groupby(['REG_imp','PROD_COMM']).agg({'cbam_cost':'sum'}).reset_index()
            cbam_cost_prev = self.V.read_var_df('cbam_cost_intermediates', year-1).groupby(['REG_imp','PROD_COMM']).agg({'cbam_cost':'sum'}).reset_index()
            cbam_cost = cbam_cost.merge(cbam_cost_prev.rename(columns={'cbam_cost':'prev'}), how='outer').fillna(0)
            cbam_cost['cbam_cost'] = cbam_cost['cbam_cost'] - cbam_cost['prev']
            cbam_cost = cbam_cost.drop(columns=['prev'])
        v_cbam = Prod_cost.calc_prod_cost_impact(MRIO_df_to_vec_DEF(cbam_cost, 'cbam_cost'))
        # ! limit ctax to 300% price increase
        v_cbam[v_cbam > 3.0] = 3.0
        v_cbam[v_cbam < -3.0] = -3.0
        cbam_eff = Price_model.second_order_dprice(v_cbam, direct_impact="passthrough")
        dp_cbam = cbam_eff['dp_full']
        v_cbam = cbam_eff['v_calculated']

        # relative increase of production cost due to tax and revenue recycling
        # ! prod_cost considering both TAX and IO change
        # exog_prod_cost = Prod_cost.calc_prod_cost(tax_rev_prod_base, recyc_rev_base)
        # v_tax = self.MRIO_df_to_vec_DEF_1(exog_prod_cost, 'prod_cost_rel')
        # v_tax = v_tax - 1
        # dp_tax = Price_model.second_order_dprice(v_tax)['dp_full']

        # ! non-tax type price change (no recycling, no energy substitution)
        # ! this only has demand effects!
        # exog_prod_cost_w_exog = Prod_cost.prod_cost_impact(Scenario.cost_shock, exog_prod_cost)
        # v_exog = self.MRIO_df_to_vec_DEF_1(exog_prod_cost_w_exog, 'prod_cost_rel')
        # v_exog = v_exog - 1
        # dp_exog = Price_model.second_order_dprice(v_exog)['dp_full']
        
        # ! calculate labor changes here(!!!)
        if year > self.model_start:
            # ! add labor cost impacts
            exog_prod_cost_w_labor = \
                Prod_cost.calc_labor_cost_impact(self.V.read_var('price_index', year-1, as_df=True),
                                                 self.V.read_var("output", year-1, as_df=True).rename(columns={'output':'q_base'}),
                                                   dlabor_sec, 
                                                   dq_total=self.V.read_var("dq_total", year, as_df=True),
                                                   dp_new=MRIO_vec_to_df_DEF(dp_all_wo_iter, 'dp_new'))
            v_labor = MRIO_df_to_vec_DEF(exog_prod_cost_w_labor, 'prod_cost_rel')
            labor_eff = Price_model.second_order_dprice(v_labor, year=year, direct_impact="passthrough")
            dp_labor = labor_eff['dp_full']
            v_labor = labor_eff['v_calculated']
        else:
            v_labor = np.zeros_like(v_exog)
            dp_labor = np.zeros_like(dp_exog)

        # ! include cost curve type effect
        # ---> need price change
        # ---> remove v_dev_normal_output + v_output_growth
        # TODO keep labour for now?

        if year > self.model_start:
            v_costcurve = MRIO_df_to_vec_DEF(cost_curves_impact, 'input_cost_change')
            # sectors to exclude from standard
            #! cost curve have to swallow labour for now
            v_no_ = MRIO_vec_to_df_DEF(v_dev_normal_output, 'v_no')
            v_og_ = MRIO_vec_to_df_DEF(v_output_growth, 'v_og')
            v_la_ = MRIO_vec_to_df_DEF(v_labor, 'v_la')
            v_pr_ = MRIO_vec_to_df_DEF(v_dev_profit_rate, 'v_pr')
            v_no_.loc[v_no_['PROD_COMM'].isin(self.cost_curve_employment),'v_no'] = 0.0
            v_og_.loc[v_og_['PROD_COMM'].isin(self.cost_curve_employment),'v_og'] = 0.0
            v_la_.loc[v_la_['PROD_COMM'].isin(self.cost_curve_employment),'v_la'] = 0.0
            v_pr_.loc[v_pr_['PROD_COMM'].isin(self.cost_curve_employment),'v_pr'] = 0.0
            v_dev_normal_output = MRIO_df_to_vec_DEF(v_no_, 'v_no')
            v_output_growth = MRIO_df_to_vec_DEF(v_og_, 'v_og')
            v_labor = MRIO_df_to_vec_DEF(v_la_, 'v_la')
            v_dev_profit_rate = MRIO_df_to_vec_DEF(v_pr_, 'v_pr')

            # labour_share = Empl_model.labour_share(dq_total = self.V.read_var("dq_total", year), 
            #                         dempl_total = dempl_total,
            #                         price_index=MRIO_df_to_vec_DEF(DYNAMIC['price_index'][year-1],'price_index'),
            #                         dp=dp_all_wo_iter)
            
            # labour_share[labour_share > 1] = 1.0
            # labour_share[labour_share < 0] = 0.0

        else:
            v_costcurve = np.zeros_like(v_exog)

        # ! dampening for stability; if iteration > 20 increase; if iteration > 50 increase again
        # dampening_factor = {
        #     5: 0.8,
        #     10: 0.6,
        #     20: 0.4,
        #     30: 0.3
        # }
        # if iter_run > 4:
        #     if iter_run in dampening_factor.keys():
        #         omega = dampening_factor[iter_run]
        #     v_costcurve = omega * v_costcurve + (1 - omega) * v_costcurve_old

        v_costcurve[v_costcurve > 2.0] = 2.0
        v_costcurve[v_costcurve < -0.5] = -0.5
        v_labor[v_labor < -0.5] = -0.5
        v_all = v_exog + v_ctax + v_dev_normal_output + v_labor + v_dev_profit_rate + v_output_growth + v_cbam + v_scarcity_rent + v_costcurve

        self.V.write_var("v_ctax", year, v_ctax)
        self.V.write_var("v_dev_normal_output", year, v_dev_normal_output)
        self.V.write_var("v_labor", year, v_labor)
        self.V.write_var("v_dev_profit_rate", year, v_dev_profit_rate)
        self.V.write_var("v_output_growth", year, v_output_growth)
        self.V.write_var("v_cbam", year, v_cbam)
        self.V.write_var("v_scarcity_rent", year, v_scarcity_rent)
        self.V.write_var("v_costcurve", year, v_costcurve)
        v_wo_cbam = v_all - v_cbam
        # ! + v_scarcity_rent (DISABLED for now)
        # v_all = v_exog + v_tax + v_dev_normal_output + v_labor + v_dev_profit_rate 

        dp_pre_trade = Price_model.second_order_dprice(v_all)['dp_full']
        self.V.write_var("v_all", year, v_all)

        dp_no_cbam = Price_model.second_order_dprice(v_wo_cbam)['dp_full']

        price_change_pre_trade = Price_model.calc_dp_pre_trade_bta(
            MRIO_vec_to_df_DEF(dp_no_cbam,'delta_p').rename(columns={'PROD_COMM':'TRAD_COMM','REG_imp':'REG_exp'}),
            self.V.read_var_df('cbam_cost_intermediates', year), ind_ener_glo, self.V.read_var('price_index', year-1, as_df=True))

        #endregion

        #region 2.2.15.3_HH_consumption_adjust [rgba(26,188,156,0.15)] 
        #region desc [rgba(26,188,156,0.50)] 
        # ^w    [2.2.15.3] HH consumption adjustment
        # ^w        new HH income and price effects
        #endregion

        if year > self.model_start:
            HH_price = HH_model.build_hh_price(price_change_pre_trade, self.V.read_var_df('emission_cost_hh', year), self.V.read_var('price_index', year-1, as_df=True), prev=self.V.read_var_df('emission_cost_hh', year-1))
        else:
            HH_price = HH_model.build_hh_price(price_change_pre_trade, self.V.read_var_df('emission_cost_hh', year), self.V.read_var('price_index', year-1, as_df=True))
        HH_price = HH_price.astype({'TRAD_COMM':'int'})
        DYNAMIC['HH_price'][year] = HH_price
        HH_price_eff, HH_inc_eff, HH_save_eff = HH_model.calc_hh_demand_change(HH_price, recyc_rev_base, Scenario.inc_exog, self.V.read_var('inc_exog', year-1, as_df=True).rename(columns={'inc_exog':'dlabor_exog'}), dlabor_inc_nat=dlabor_nat, year=year)

        dy_hh_price = IO_model.build_dy_hh(HH_price_eff, 'delta_y_price')
        dy_hh_inc = IO_model.build_dy_hh(HH_inc_eff, 'delta_y_inc')
        dy_hh_save = IO_model.build_dy_hh(HH_save_eff, 'delta_y_save')

        #endregion

        #region 2.2.15.4_GOV_adjust [rgba(26,188,156,0.2)] 
        #region desc [rgba(26,188,156,0.50)] 
        # ^w    [2.2.15.4] Government adjustment
        #endregion

        # Construct government model
        GOV_recyc = GOV_model.calc_gov_demand_change(recyc_rev_base, self.V.read_var('price_index', year-1) + dp_pre_trade)
        dy_gov_recyc = MRIO_df_to_vec(GOV_recyc.reset_index(), 'REG_exp', 'TRAD_COMM', 'delta_y_gov', EXOG_VARS.R['Region_acronyms'].to_list(), EXOG_VARS.P['Lfd_Nr'].to_list())
        
        # Calculate new final demand due to investment
        INV_model.calc_dy_inv_recyc(recyc_rev_base, self.V.read_var('price_index', year-1) + dp_pre_trade)
        dy_inv_recyc = MRIO_df_to_vec(INV_model.dy_inv_recyc,"REG_exp", "TRAD_COMM",
                                    "dy", EXOG_VARS.R['Region_acronyms'].to_list(), EXOG_VARS.P['Lfd_Nr'].to_list())

        #endregion

        #region 2.2.15.5_Trade_recalculation [rgba(26,188,156,0.15)] 
        #region desc [rgba(26,188,156,0.50)] 
        # ^w    [2.2.15.5] Trade recalculation (new prices)
        #endregion

        ind_trade = Trade_model.calc_IO_coef(ind_ener_glo, price_change_pre_trade, year)
        # calculate FD substitution
        fd_trade_response = Trade_model.calc_FD_substitution(price_change_pre_trade)
        dy_trade_hh = fd_trade_response['dy']['dy_trade_hh']
        dy_trade_fcf = fd_trade_response['dy']['dy_trade_fcf']
        dy_trade_gov = fd_trade_response['dy']['dy_trade_gov']

        # Build new A matrix due to trade (import) substitution

        # add scenario based changes
        # ind_trade = IO_model.io_change(io_changes, ind_trade)
        A_trade = IO_model.build_A_matrix(input_df=ind_trade, variable='IO_coef_trade')
        IO_model.update_Leontieff(A_trade)
        dq_trade_eff = IO_model.calc_dq_trade((dq_tech_eff))
        self.V.write_var("dq_trade_eff", year, dq_trade_eff)

        Price_model.update_A_BASE(A_trade)
        Price_model.calc_positive_and_negative_L()

        # Calculate output changes for each driver of output change
        trade_dy = dy_trade_hh + dy_trade_fcf + dy_trade_gov
        # dq_IO_eff = IO_model.calc_dq_IO(trade_dy)

        # dq_trade_eff is calculated as = dq_IO_eff - dq_tech_eff
        # then calculate HH impacts of trade
        dq_trade_hh = IO_model.calc_dq_exog(dy_trade_hh)
        dq_trade_fcf = IO_model.calc_dq_exog(dy_trade_fcf)
        dq_trade_gov = IO_model.calc_dq_exog(dy_trade_gov)
        self.V.write_var("dq_trade_hh", year, dq_trade_hh)
        self.V.write_var("dq_trade_fcf", year, dq_trade_fcf)
        self.V.write_var("dq_trade_gov", year, dq_trade_gov)
        
        dq_hh_price, dq_hh_inc, dq_hh_save = IO_model.calc_dq_hh(dy_hh_price, dy_hh_inc, dy_hh_save)
        self.V.write_var("dq_hh_price", year, dq_hh_price)
        self.V.write_var("dq_hh_inc", year, dq_hh_inc)
        self.V.write_var("dq_hh_save", year, dq_hh_save)

        # V.w("dq_hh_price", dq_hh_price, "IO_model_iter_{}".format(iter_run))
        dq_gov_delta = IO_model.calc_dq_exog(dy_gov_delta)
        dq_gov_recyc = IO_model.calc_dq_gov(dy_gov_recyc)
        self.V.write_var("dq_gov_delta", year, dq_gov_delta)
        self.V.write_var("dq_gov_recyc", year, dq_gov_recyc)

        dp_all = Price_model.second_order_dprice(v_all)['dp_full']
        self.V.write_var("dp_all", year, dp_all)
        #endregion

        #region 2.2.15.6_Investment [rgba(26,188,156,0.2)] 
        #region desc [rgba(26,188,156,0.50)] 
        # ^w    [2.2.15.6] Induced investment
        #endregion

        # Calculate output changes due to investment
        dq_inv_induced, dq_inv_recyc, dq_inv_exog = IO_model.calc_dq_inv(DYNAMIC['dy_inv_induced_L1'], dy_inv_recyc, dy_inv_exog)
        self.V.write_var("dq_inv_exog", year, dq_inv_exog)
        self.V.write_var("dq_inv_recyc", year, dq_inv_recyc)
        self.V.write_var("dq_inv_induced", year, dq_inv_induced)

        #endregion
        dq_total = (dq_trade_eff + dq_tech_eff + dq_hh_price + dq_hh_inc + dq_hh_save + dq_hh_exog + dq_gov_recyc + dq_gov_delta + 
                    dq_inv_induced + dq_inv_recyc + dq_inv_exog + dq_hh_exog_fd +
                    dq_fcf_exog_fd + dq_gov_exog_fd + dq_calibration_residual + dq_structural_change + dq_hh_tech_substitution)
        self.V.write_var("dq_total", year, dq_total)

        supply_constraint = IO_model.calc_dq_supply_constraint3(Scenario.supply_constraint, q_base=(IO_model.q_base+dq_total))
        dq_supply_constraint = supply_constraint['dq_supply_constraint']

        supply_constraint_no_empl = IO_model.calc_dq_supply_constraint(Scenario.supply_constraint_no_empl_change, q_base=(IO_model.q_base+dq_total))
        dq_supply_constraint_no_empl = supply_constraint_no_empl['dq_supply_constraint']

        #region 2.2.15.7_Total_calc [rgba(26,188,156,0.15)] 
        #region desc [rgba(26,188,156,0.50)] 
        # ^w    [2.2.15.7] Calculate totals, check whether within threshold
        #endregion
        # Re-calculate dq_total
        dq_total = (dq_trade_eff + dq_tech_eff + dq_hh_price + dq_hh_inc + dq_hh_save + dq_hh_exog + dq_gov_recyc + dq_gov_delta + dq_calibration_residual + 
                dq_inv_induced + dq_inv_recyc + dq_inv_exog + dq_hh_exog_fd + dq_fcf_exog_fd + dq_gov_exog_fd + dq_supply_constraint +  
                dq_structural_change + dq_supply_constraint_no_empl + dq_hh_tech_substitution)
        self.V.write_var("dq_total", year, dq_total)

        #! io change comes here
        # add scenario based changes
        #! add cost curves to IO changes
        if year > self.model_start:
            io_changes_ = pd.concat([io_changes, cost_curves_io], axis=0)
        else:
            io_changes_ = io_changes

        ind_ener_iter = IO_model.io_change(io_changes_, ind_trade)
        # ind_trade = ind_ener_iter

        # ! SET IO
        A_iochange = IO_model.build_A_matrix(input_df=ind_ener_iter, variable='IO_coef_trade')
        fd_vec_tmp = IO_model.calc_fd_vec(dq_total+IO_model.q_base_curr)
        IO_model.update_Leontieff(A_iochange)
        dq_io_change = IO_model.calc_dq_io((dq_total+IO_model.q_base_curr), fd_vec_tmp)

        dq_total_empl = (dq_trade_eff + dq_tech_eff + dq_hh_price + dq_hh_inc + dq_hh_save + dq_hh_exog + dq_gov_recyc + dq_gov_delta + 
        dq_inv_induced + dq_inv_recyc + dq_inv_exog + dq_hh_exog_fd +
        dq_fcf_exog_fd + dq_gov_exog_fd + dq_supply_constraint + dq_calibration_residual + dq_structural_change_wo_employment + dq_hh_tech_substitution + dq_io_change)
        
        dq_total = (dq_trade_eff + dq_tech_eff + dq_hh_price + dq_hh_inc + dq_hh_save + dq_hh_exog + dq_gov_recyc + dq_gov_delta + dq_calibration_residual + 
                dq_inv_induced + dq_inv_recyc + dq_inv_exog + dq_hh_exog_fd + dq_fcf_exog_fd + dq_gov_exog_fd + dq_supply_constraint +  
                dq_structural_change + dq_supply_constraint_no_empl + dq_hh_tech_substitution + dq_io_change)
        self.V.write_var("dq_total", year, dq_total)
        
        dempl = Empl_model.calc_dempl({
            'total':                dq_total_empl,
            'tech_eff':             dq_tech_eff,
            'trade_eff':            dq_trade_eff,
            'trade_hh':             dq_trade_hh,
            'trade_gov':            dq_trade_gov,
            'trade_fcf':            dq_trade_fcf,
            'hh_price':             dq_hh_price,
            'hh_inc':               dq_hh_inc,
            'hh_save':              dq_hh_save,
            'hh_exog':              dq_hh_exog,
            'gov_recyc':            dq_gov_recyc,
            'gov_delta':            dq_gov_delta,
            'inv_induced':          dq_inv_induced,
            'inv_recyc':            dq_inv_recyc,
            'inv_exog':             dq_inv_exog,
            'hh_exog_fd':           dq_hh_exog_fd,
            'fcf_exog_fd':          dq_fcf_exog_fd,
            'gov_exog_fd':          dq_gov_exog_fd,
            'supply_constraint':    dq_supply_constraint,
            'calibration_residual': dq_calibration_residual,
            'structural_change':    dq_structural_change_wo_employment,
            'hh_tech_substitution': dq_hh_tech_substitution,
            'io_change':            dq_io_change,
        })
        dempl_total               = dempl['total']
        dempl_tech_eff            = dempl['tech_eff']
        dempl_trade_eff           = dempl['trade_eff']
        dempl_trade_hh            = dempl['trade_hh']
        dempl_trade_gov           = dempl['trade_gov']
        dempl_trade_fcf           = dempl['trade_fcf']
        dempl_hh_price            = dempl['hh_price']
        dempl_hh_inc              = dempl['hh_inc']
        dempl_hh_save             = dempl['hh_save']
        dempl_hh_exog             = dempl['hh_exog']
        dempl_gov_recyc           = dempl['gov_recyc']
        dempl_gov_delta           = dempl['gov_delta']
        dempl_inv_induced         = dempl['inv_induced']
        dempl_inv_recyc           = dempl['inv_recyc']
        dempl_inv_exog            = dempl['inv_exog']
        dempl_hh_exog_fd          = dempl['hh_exog_fd']
        dempl_fcf_exog_fd         = dempl['fcf_exog_fd']
        dempl_gov_exog_fd         = dempl['gov_exog_fd']
        dempl_supply_constraint   = dempl['supply_constraint']
        dempl_calibration_residual = dempl['calibration_residual']
        dempl_structural_change   = dempl['structural_change']
        dempl_hh_tech_substitution = dempl['hh_tech_substitution']
        dempl_io_change           = dempl['io_change']
        
        if year == 2020 or year == 2021:
            dempl_total = dempl_total - dempl_calibration_residual
            dempl_calibration_residual = np.zeros_like(dempl_calibration_residual)
        
        # ! productivity change in employment is NOT output based
        dempl_total = dempl_total + dempl_productivity
        
        # ! need to account for labour supply constraint, we set it as == UNEMP min 1% of LF
        employment_constraint = Empl_model.calc_dempl_constraint(
            self.V.read_var("employment_base", year),
            dempl_total,
            np.zeros_like(dempl_total),
            self.V.read_var("output", year-1),
            dq_total,
            self.V.read_var('labour_force', year, as_df=True).rename(columns={'labour_force':'LF'}),
            self.V.read_var("shadow_nat_employment", year-1, as_df=True), year
        )
        dL_before = dempl_labour_supply_constraint.copy()
        dempl_labour_supply_constraint = employment_constraint['dL']
        self.V.write_var("shadow_unemployment_rate", year, employment_constraint['shadow_unemployment_rate'], from_df=True)
        self.V.write_var('shadow_nat_employment', year, employment_constraint['shadow_employment'], from_df=True)
        empl_labour_supply_constraint = IO_model.calc_dq_supply_constraint2(employment_constraint['dQ'], dq_total)
        dq_empl_labour_supply_constraint = empl_labour_supply_constraint['dq']

        # ! need to adjust consumption as well
        # dy_empl_labour_supply_constraint = empl_labour_supply_constraint['dy']
        # empl_LSC_dy = MRIO_vec_to_df_DEF(dy_empl_labour_supply_constraint, 'dy').rename(columns={'REG_imp':'REG_exp','PROD_COMM':'TRAD_COMM'})
        # REG_exp | TRAD_COMM | dy

        # TODO : move from here!

        # hh_cons = HH_model.HH.reset_index() # VIPA
        # fcf_cons = INV_model.FCF.reset_index() # VDFA
        # gov_cons = GOV_model.GOV[['REG_imp','REG_exp','TRAD_COMM','VIGA']] # VIGA

        # cons = hh_cons.merge(fcf_cons, how='outer').merge(gov_cons, how='outer')
        # cons['total'] = cons['VIGA'] + cons['VIPA'] + cons['VDFA']
        # cons['gov_share'] = cons['VIGA'] / cons['total']
        # cons['hh_share'] = cons['VIPA'] / cons['total']
        # cons['fcf_share'] = cons['VDFA'] / cons['total']

        # fd_df = cons.merge(empl_LSC_dy, how='left', on=['REG_exp','TRAD_COMM'])
        # fd_df['total_row'] = (fd_df['total'] / fd_df.groupby(['REG_exp','TRAD_COMM'])['total'].transform('sum')) * fd_df['dy']

        # fd_df['VIPA_new'] = fd_df['total_row'] * fd_df['hh_share']
        # fd_df['VIGA_new'] = fd_df['total_row'] * fd_df['gov_share']
        # fd_df['VDFA_new'] = fd_df['total_row'] * fd_df['fcf_share']

        # # make sure that consumption per row doesn't go negative
        # fd_df.loc[(fd_df['VIGA_new'] + fd_df['VIGA']) < 0.0, 'VIGA_new'] = fd_df.loc[(fd_df['VIGA_new'] + fd_df['VIGA']) < 0.0, 'VIGA'] * -0.9
        # fd_df.loc[(fd_df['VIPA_new'] + fd_df['VIPA']) < 0.0, 'VIPA_new'] = fd_df.loc[(fd_df['VIPA_new'] + fd_df['VIPA']) < 0.0, 'VIPA'] * -0.9
        # fd_df.loc[(fd_df['VDFA_new'] + fd_df['VDFA']) < 0.0, 'VDFA_new'] = fd_df.loc[(fd_df['VDFA_new'] + fd_df['VDFA']) < 0.0, 'VDFA'] * -0.9

        # fd_df = fd_df.drop(columns=['VIPA','VIGA','VDFA']).rename(columns={'VIGA_new':'VIGA','VIPA_new':'VIPA','VDFA_new':'VDFA'})

        # dy_hh_empl_LSC = fd_df[['REG_exp','REG_imp','TRAD_COMM','VIPA']].rename(columns={'VIPA':'dy_LSC'})
        # dy_fcf_empl_LSC = fd_df[['REG_exp','REG_imp','TRAD_COMM','VIGA']].rename(columns={'VIGA':'dy_LSC'})
        # dy_gov_empl_LSC = fd_df[['REG_exp','REG_imp','TRAD_COMM','VDFA']].rename(columns={'VDFA':'dy_LSC'})

        # -----------------------------------------------------------------------------------------
        
        # dq_total_iter = pd.concat([dq_total_iter, pd.DataFrame(
        #     dq_total, columns = [f"dq_{iter_run}"])], axis=1)

        # dempl_total_iter = pd.concat([dempl_total_iter, pd.DataFrame(
        #     dempl_total, columns = [f"dempl_{iter_run}"])], axis=1)
        
        # dlabor_iter = pd.concat([dlabor_iter, pd.DataFrame(
        #     dlabor_sec, columns = [f"dlabor_{iter_run}"])], axis=1)
        
        if iter_run > 1:
            labor_cond = np.nan_to_num(np.max(np.abs((dlabor_nat['dlabor'] / dlabor_nat['dlabor_before']) - 1)))
        else:
            labor_cond = np.inf

        if iter_run > 1:
            labor_constraint_cond = np.nan_to_num(np.max(np.abs((employment_constraint['dL'] / dL_before) - 1)))
        else:
            labor_constraint_cond = np.inf

        if iter_run > 1:
            price_cond = np.max(np.abs(np.nan_to_num((dp_all - dp_all_old))))

            DEBUG = True
            if DEBUG:
                pd.DataFrame({
                    'output': dq_total,
                    'empl': dempl_total,
                    'current': dp_all,
                    'old': dp_all_old,
                    'v_all': v_all,
                    'v_labor': v_labor,
                    'v_dev_normal_output': v_dev_normal_output, 
                    'v_costcurve': v_costcurve,
                    'dq_empl_constraint': dq_empl_labour_supply_constraint,
                    'dq_hh_inc': dq_hh_inc,
                    'dq_hh_price': dq_hh_price,
                    'dq_hh_save': dq_hh_save,
                    'dq_total_empl': dq_total_empl,
                    'dq_trade_eff': dq_trade_eff,
                    'dq_io_change': dq_io_change,
                    'empl_constraint': employment_constraint['dL'],
                    'v_output_growth': v_output_growth}).to_csv("Temp\\iter{}-{}.csv".format(year, iter_run))
        else:
            price_cond = np.inf
        
        # tax_rev_cond = 0
        if iter_run > 1:
            tax_rev_cond = max(np.nan_to_num(abs(MRIO_df_to_vec_DEF(dtax_rev, 'emission_cost')), nan=0.0))
        else:
            tax_rev_cond = np.inf

        print(f"--- 2.2.15 Iteration #{iter_run}: {round(time.time() - iter_time, 1)} seconds ---")
        print(f"--- 2.2.15 Labor compensation relative diff.: {round(labor_cond * 100, 4)}% ---")
        print(f"--- 2.2.15 Tax revenue relative diff.: {round(tax_rev_cond * 100, 4)}% ---")
        print(f"--- 2.2.15 Price change relative diff.: {round(price_cond * 100, 4)}% ---")
        print(f"--- 2.2.15 Labour constraint diff.: {round(labor_constraint_cond * 100, 4)}% ---")
        print(f"--- 2.2.15 MRIO matrix relative diff.: {round(np.max(np.abs(np.nan_to_num(A_old - A_trade, nan=0))) * 100, 4)}pp ---")

        if ((labor_cond < self.COND_LABOR and tax_rev_cond < self.COND_TAX and price_cond < self.COND_PRICE and
            np.allclose(A_old, A_trade, atol=self.COND_TRADE)) or (iter_run > self.ITER_MAX)):
            break
        
        iter_run += 1

        #endregion
    # If the iteration loop never ran, persist emission/cbam costs to self.V for cross-year reads
    if not self.SWITCH_WITHIN_YEAR_LOOP:
        for suffix in ('intermediates', 'hh', 'fcf', 'gov'):
            self.V.write_var_df(f'emission_cost_{suffix}', year, emission_cost_dfs[suffix])
            self.V.write_var_df(f'cbam_cost_{suffix}', year, cbam_cost_dfs[suffix])

    dq_total = dq_total + dq_empl_labour_supply_constraint
    dempl_total = dempl_total + dempl_labour_supply_constraint + dempl_costcurve

    DYNAMIC['dq_supply_constraint_no_empl'] = dq_supply_constraint_no_empl

    # Write all dempl_* variables to self.V (single source of truth per variables.xlsx)
    for _name, _val in [
        ('dempl_total',                    dempl_total),
        ('dempl_tech_eff',                 dempl_tech_eff),
        ('dempl_trade_eff',                dempl_trade_eff),
        ('dempl_trade_hh',                 dempl_trade_hh),
        ('dempl_trade_gov',                dempl_trade_gov),
        ('dempl_trade_fcf',                dempl_trade_fcf),
        ('dempl_hh_price',                 dempl_hh_price),
        ('dempl_hh_inc',                   dempl_hh_inc),
        ('dempl_gov_recyc',                dempl_gov_recyc),
        ('dempl_gov_delta',                dempl_gov_delta),
        ('dempl_inv_induced',              dempl_inv_induced),
        ('dempl_inv_recyc',                dempl_inv_recyc),
        ('dempl_inv_exog',                 dempl_inv_exog),
        ('dempl_hh_exog_fd',               dempl_hh_exog_fd),
        ('dempl_fcf_exog_fd',              dempl_fcf_exog_fd),
        ('dempl_gov_exog_fd',              dempl_gov_exog_fd),
        ('dempl_supply_constraint',        dempl_supply_constraint),
        ('dempl_calibration_residual',     dempl_calibration_residual),
        ('dempl_structural_change',        dempl_structural_change),
        ('dempl_hh_tech_substitution',     dempl_hh_tech_substitution),
        ('dempl_productivity',             dempl_productivity),
        ('dempl_costcurve',                dempl_costcurve),
        ('dempl_labour_supply_constraint', dempl_labour_supply_constraint),
    ]:
        self.V.write_var(_name, year, _val)

    #endregion
    #endregion
    #endregion
    return Scenario, HH_model, GOV_model, INV_model, IO_model, Inc_model, Empl_model, \
        HH_price, HH_price_eff, HH_inc_eff, HH_tech_substitution, GOV_recyc, Prod_cost, \
        INV_CONV, ener_base, self.V.read_var("dp_all",year), self.V.read_var("dq_total", year), A_iochange, fd_trade_response, dp_ctax, \
        supply_constraint, supply_constraint_no_empl, dlabor_sec, profit_rate_mean_L1, \
        dq_supply_constraint, dq_supply_constraint_no_empl, self.V.read_var("dq_tech_eff",year), self.V.read_var("dq_trade_eff",year), \
        self.V.read_var("dq_trade_hh", year), self.V.read_var("dq_trade_gov", year), self.V.read_var("dq_trade_fcf", year), \
        self.V.read_var("dq_hh_price", year), self.V.read_var("dq_hh_inc", year), self.V.read_var("dq_hh_save", year), dq_hh_exog,\
        self.V.read_var("dq_gov_recyc", year), \
        self.V.read_var("dq_gov_delta", year), self.V.read_var("dq_inv_induced", year), self.V.read_var("dq_inv_recyc", year), self.V.read_var("dq_inv_exog", year), dq_hh_exog_fd, \
        dq_fcf_exog_fd, dq_gov_exog_fd, dq_calibration_residual, \
        dq_structural_change, dq_hh_tech_substitution, dq_io_change
