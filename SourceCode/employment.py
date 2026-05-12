# -*- coding: utf-8 -*-
"""
Created on Fri Jun 30 11:36:56 2023

@author: wb582890
"""

import numpy as np
import pandas as pd
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df
from copy import deepcopy

class empl:
    """
    This class collects the variables and parameters related to employment and calculates base employment,
    employment constraints, and employment changes.

    Parameters
    ----------
    EXOG_VARS : class
        Class for exogenous variables.
    
    Methods
    -----------
    recalc_empl_base
        Re-calculates employment base based on output base and employment multipliers in the first period of the simulation.
    calc_dempl_constraint
        Applies employment constraints and calculates shadow unemployment rate.
    calc_unemployment
        Calculates unemployment based on labour force and employment.
    adjust_labor_productivity
        Applies adjustment to labour productivity.
    calc_dempl
        Calculates changes in employment.
    """ 
    def __init__(self, EXOG_VARS, exclude_sectors):
        # load the following:
        # q_base, capital_stock, PARAMETERS
        self.R = EXOG_VARS.R
        self.R_list = EXOG_VARS.R_list
        self.P_list = EXOG_VARS.P_list

        self.exclude_sectors = exclude_sectors

        self.LABOR_BASE = EXOG_VARS.LABOR_BASE

        self.common = None

        # set up params
        params = deepcopy(EXOG_VARS.PARAMETERS)
        params.loc[params['PROD_COMM'].isin(self.exclude_sectors), params.columns[3:]] = 0.0
        load_param = lambda var_: MRIO_df_to_vec(params,'REG_imp','PROD_COMM', var_ ,self.R_list,self.P_list)

        self.params = {}
        self.params['Q_ln'] = load_param('employment_Q_ln')
        self.params['W_ln_L1'] = load_param('employment_W_ln_L1')
        self.params['K_ln_L1'] = load_param('employment_K_ln_L1')

        self.MRIO_vec_to_df_DEF = lambda vec,name: MRIO_vec_to_df(vec, name, len(EXOG_VARS.P), EXOG_VARS.R)\
                .rename(columns={'target-sector':'PROD_COMM','target-country-iso3':'REG_imp'}).drop(columns=['target-country'])
        
    def calc_initial(self):
        # employment and wages
        labor = self.LABOR_BASE.copy()

        # aggregate labor
        labor = labor.set_index(['REG_imp','PROD_COMM'])
        labor['employment_base'] = labor[[x for x in labor.columns if 'vol' in x]].sum(axis=1)
        labor = labor[['employment_base']]
        labor = labor.reset_index()

        return labor

    def load_dynamic(self, vars_):
        if self.common is None:
            self.common = {}
        for k,v in vars_.items():
            self.common[k] = v
    
    def recalc_empl_base(self, q_base):
        # re-calculate empl base based on q_base; and empl_multiplier calculated in first period
        # don't forget that if productivity changes, that means changes for the base too not just delta

        # base part 
        empl_t0 = np.nan_to_num(q_base / self.labor_productivity, posinf=0, neginf=0)
        return empl_t0
    
    def calc_dempl_constraint(self, employment_, dempl_total_, dempl_prev_, output_, dq_total_, labour_force, shadow_empl_, year):
        """
        AI overview of the function (checked by BKD on 2026-03-20):
            1.  Base overemployment check. For each region, compare current (base) national employment to 99% of the labour force. Regions already overemployed get 
                a proportional downward adjustment per sector to bring them back to the threshold. Regions not overemployed pass through unchanged.
                
            2.  Merge demand shock. Attach the demand-driven employment change (dempl) to each sector-region, then reconcile it with the adjustment: if a sector is
                already shedding workers via dempl, it partially or fully absorbs the adjustment so the two don't double-count.
                
            3.  Post-shock overemployment check. Recompute national employment after both adjustment and dempl are applied. Regions that are still overemployed after
                the shock form the constrained group (e_c); the rest are left unchanged (e_unchanged).

            4.  Distribute the constraint across growing sectors. Within the constrained group, compute each sector's share of total regional employment growth (growth_share).
                Multiply by over_full_employment to get a sector-level growth_constraint — the amount by which each growing sector's employment must be reduced.

            5.  Weight the constraint by relative growth rate. Scale growth_constraint by each sector's growth rate relative to the fastest-growing sector in the region (demand_growth_scale),
                so faster-growing sectors absorb more of the constraint. Rescale to ensure the total constraint is preserved (scale).

            6.  Cap at sector dempl. If applying the constraint would push a sector's net employment change negative (i.e., constraint exceeds the growth), cap it at exactly
                dempl for that sector and flag it (flag=1).

            7.  Rescale unconstrained growing sectors. The capped sectors (flag=1) have absorbed less constraint than originally assigned. Redistribute the shortfall to the
                remaining growing sectors (flag=0) via scale1, so the total regional constraint is still fully met.
                
            8.  Handle loss sectors and unchanged regions. Sectors already losing workers in constrained regions get dempl_constraint = 0 (no additional constraint needed). 
                Regions that were not overemployed after the shock also get dempl_constraint = 0.

            9. Assemble final output. Combine all groups, adding adjustment and dempl_constraint together for constrained regions to produce the final employment constraint vector.
        """
        # employment is the vector of employment
        # labour force is LF data.frame by country
        employment_vec = deepcopy(employment_) # just base!
        dq_total = deepcopy(dq_total_)
        dempl_total_vec = deepcopy(dempl_total_)
        output_vec = deepcopy(output_)

        # 1. do overemployment in the base, before dempl
        employment = self.MRIO_vec_to_df_DEF(employment_vec, 'employment_base')
        employment['nat_employment'] = employment.groupby('REG_imp')['employment_base'].transform('sum')
        employment = employment.merge(labour_force, how='left', on='REG_imp') # LF 
        employment['over_full_employment1'] = employment['nat_employment'] - (employment['LF'] * 0.99) #? this is a positive number if over
        employment['flag_over_base'] = 0
        employment.loc[employment['over_full_employment1'] > 0, 'flag_over_base'] = 1
        employment.loc[employment['flag_over_base'] == 0, 'over_full_employment1'] = 0.0

        # split into change and unchanged
        e_unchanged = employment[employment['flag_over_base']==0].copy()
        e_c = employment[employment['flag_over_base']==1].copy()
        del employment

        e_c['adjustment'] = -1 * (e_c['over_full_employment1'] * (e_c['employment_base'] / e_c['nat_employment']))

        # 2. re-create full
        e_unchanged['adjustment'] = 0.0
        cols = ['REG_imp','PROD_COMM','LF','nat_employment','employment_base','adjustment']

        employment = pd.concat([e_c[cols], e_unchanged[cols]])
        # -----------------------

        # 4. now recalculate overemployment with dempl added

        dempl_total = self.MRIO_vec_to_df_DEF(dempl_total_vec, 'dempl')
        employment = employment.merge(dempl_total, how='left', on=['REG_imp','PROD_COMM'])

        # 5. first we need to make adjustments, if sectors are already loosing employment (dempl) then they don't need to adjust (adjustment)
        # reallocate if dempl is negative; e.e., we have released workers who can pick up work where other jobs are lost
        # look at cases where dempl_total is negative
        # [negative space] in these cases if dempl_total > adjustment, the dempl_total swallows adjustment
        # [negative space] if dempl_total < adjustment then adjustment is 
        mask = (employment['dempl'] < 0) & (employment['adjustment'] >= employment['dempl'])
        employment.loc[mask, 'adjustment'] = 0.0
        mask = (employment['dempl'] < 0) & (employment['adjustment'] < employment['dempl'])
        employment.loc[mask, 'adjustment'] = employment.loc[mask, 'adjustment'] + employment.loc[mask, 'dempl']

        # this gets rid of 'double-counting'

        employment['nat_employment_with_dempl'] = employment['nat_employment'] + employment.groupby(['REG_imp'])['adjustment'].transform('sum') + employment.groupby(['REG_imp'])['dempl'].transform('sum')
        employment['over_full_employment'] = employment['nat_employment_with_dempl'] - (employment['LF'] * 0.99) #? this is a positive number if over
        # ? this is how many ppl would be needed extra, but don't have

        employment['flag_over_dempl'] = 0
        employment.loc[employment['over_full_employment'] > 0, 'flag_over_dempl'] = 1
        employment.loc[employment['flag_over_dempl'] == 0, 'over_full_employment'] = 0.0

        # split into change and unchanged
        e_unchanged = employment[employment['flag_over_dempl']==0].copy()
        e_c = employment[employment['flag_over_dempl']==1].copy()
        del employment

        # 6. share out growth TODO - method?
        e_c['base_loss'] = 0.0
        mask = e_c['dempl'] < 0
        e_c.loc[mask, 'base_loss'] = e_c.loc[mask, 'dempl']
        e_c['nat_base_loss'] = e_c.groupby(['REG_imp'])['base_loss'].transform('sum')

        e_c['base_growth'] = 0.0
        mask = e_c['dempl'] > 0
        e_c.loc[mask, 'base_growth'] = e_c.loc[mask, 'dempl']
        e_c['growth_share'] = e_c['base_growth'] / e_c.groupby(['REG_imp'])['base_growth'].transform('sum')

        # goal is to reduce over_full_employment
        e_c['nat_constraint'] = e_c['over_full_employment'] # + e_c['nat_base_loss'] ?
        e_c['growth_constraint'] = -1.0 * (e_c['nat_constraint'] * e_c['growth_share'])
        mask = e_c['growth_constraint'] > 0
        e_c.loc[mask, 'growth_constraint'] = 0.0

        # split into growth/loss
        e_c_g = e_c[e_c['dempl'] >= 0].copy() # no loss
        e_c_l = e_c[e_c['dempl'] < 0].copy()

        # 7.  adjust with growth
        # e_c_g['demand_growth_scale'] = np.nan_to_num((e_c_g['dempl'] / e_c_g['employment_base']), nan=0)
        # e_c_g['demand_growth_scale'] = e_c_g['demand_growth_scale'] / e_c_g.groupby(['REG_imp'])['demand_growth_scale'].transform("max")
        # 0-1
        # e_c_g['growth_constraint_adj'] = e_c_g['growth_constraint'] * e_c_g['demand_growth_scale']
        # e_c_g['scale'] = np.nan_to_num(e_c_g.groupby(['REG_imp'])['growth_constraint'].transform("sum") / e_c_g.groupby(['REG_imp'])['growth_constraint_adj'].transform("sum"), neginf=0, posinf=0, nan=0)
        # e_c_g['growth_constraint_adj'] = e_c_g['growth_constraint_adj'] * e_c_g['scale']
        # adjust with dempl

        # 8. exclude negative resulting dempl
        mask = (e_c_g['dempl'] - e_c_g['growth_constraint']) < 0
        e_c_g.loc[mask, 'growth_constraint'] = e_c_g.loc[mask, 'dempl'] * -1.0
        e_c_g['flag'] = 0.0
        e_c_g.loc[mask, 'flag'] = 1.0

        # rescale
        if(len(e_c_g[mask]) > 0):
            emp_nat = e_c_g.groupby(['REG_imp','flag']).agg({'nat_constraint':'mean', 'growth_constraint':'sum'}).reset_index()
            emp_nat = emp_nat.pivot(index=['REG_imp'], columns='flag', values=['nat_constraint','growth_constraint']).reset_index()
            emp_nat.columns = ['REG_imp','nat_constraint','drop','flag0','flag1']
            emp_nat['flag1'] = emp_nat['flag1'].fillna(0)
            emp_nat = emp_nat.drop(columns=['drop'])
            emp_nat['scale1'] = np.nan_to_num((emp_nat['nat_constraint'] - emp_nat['flag1']) / emp_nat['flag0'], posinf=0, neginf=0, nan=0)

            e_c_g = e_c_g.merge(emp_nat[['REG_imp','scale1']], how='left')
        else:
            e_c_g['scale1'] = 1.0
        
        m = e_c_g['flag']==0
        e_c_g.loc[m, 'growth_constraint'] = e_c_g.loc[m, 'scale1'] * e_c_g.loc[m, 'growth_constraint']
        e_c_g['dempl_constraint'] = e_c_g['growth_constraint']

        # 9. handle loss sectors
        e_c_l['dempl_constraint'] = 0.0

        # 10. construct df and then vector
        cols = ['REG_imp','PROD_COMM','dempl','employment_base','adjustment','dempl_constraint']
        e_c = pd.concat([e_c_g[cols], e_c_l[cols]])

        e_unchanged['dempl_constraint'] = 0.0
        cols = ['REG_imp','PROD_COMM','dempl','employment_base','dempl_constraint','adjustment']
        employment = pd.concat([e_c[cols],e_unchanged[cols]])
        employment['dempl_constraint'] = employment['adjustment'] + employment['dempl_constraint']
        
        cols = ['REG_imp','PROD_COMM','dempl','employment_base','dempl_constraint']
        employment = employment[cols].copy()

        # ! shadow_employment
        # ---------------------------------------------------------------------------
        # REG_imp | shadow_nat_employment
        # ? employment_base mean here is not real mean, value is only REG_imp, not sector specific
        # shadow_empl = shadow_empl_.copy()
        shadow_empl = employment[['REG_imp','dempl','employment_base']].copy()
        shadow_empl = shadow_empl.groupby(['REG_imp']).agg({'dempl':'sum','employment_base':'sum'}).reset_index()

        shadow_empl['shadow_nat_employment'] = shadow_empl['dempl'] + shadow_empl['employment_base']
        shadow_empl = shadow_empl[['REG_imp','shadow_nat_employment']].copy()

        # ! calc unemp w/ shadow employment
        unemp_rate = shadow_empl.merge(labour_force, how='left', on='REG_imp')
        unemp_rate['shadow_unemployment_rate'] = 1 - (unemp_rate['shadow_nat_employment'] / unemp_rate['LF'])
        unemp_rate = unemp_rate[['REG_imp','shadow_unemployment_rate']].copy()
        # ---------------------------------------------------------------------------

        # negative * positive = negative
        # dempl['adjustment'] = dempl['dempl'] * -1.0

        # ! calculate reverse output impact
        dempl_vec = MRIO_df_to_vec(employment, 'REG_imp', 'PROD_COMM', 'dempl_constraint', self.R_list, self.P_list)
        # dL must be negative
        dL = dempl_vec / (employment_vec+dempl_total_vec)
        # Q_ln is always positive
        dQ = dL * self.params['Q_ln']
        dQ[dQ < -1.0] = -1.0
        if np.any(dQ > 1.0):
            print("dQ is high; i.e. we're increasing output by more than 100 percent as a results of labour constraint - SURE?")
        # dQ is inf > dQ > -1.0
        q = (output_vec + dq_total)
        dQ = dQ * q
        dQ = np.nan_to_num(dQ)

        return({
            'dL': dempl_vec,
            'dQ': dQ,
            'shadow_unemployment_rate': unemp_rate,
            'shadow_employment': shadow_empl
            })
    
    def calc_unemployment(self, employment, labour_force):
        # employment is the vector of employment
        # labour force is LF data.frame by country

        employment = employment.groupby('REG_imp').agg({'employment_base':'sum'}).reset_index()
        employment = employment.merge(labour_force, how='left', on='REG_imp')

        employment['unemployment_rate'] = 1 - employment['employment_base'] / employment['LF']
        employment = employment[['REG_imp','unemployment_rate']].copy()
        
        return employment
    
    def recalc_empl_base_NEW(self):
        # re-calculate empl based on q_base; productivity changes are coming through econometrics
        # note: Q is fixed; K, K-1 is changing
        dK = np.nan_to_num(self.common['k'] / self.common['k1'], nan=1.0, posinf=1.0, neginf=1.0) - 1

        wage = self.common['wage'].merge(self.common['wage_prev1'].rename(columns={'wage':'wage_prev1'}))
        wage = wage.merge(self.common['cpi'].merge(self.common['cpi_prev1'].rename(columns={'cpi':'cpi_prev1'})))
        wage['d_wage'] = (wage['wage'] / wage['cpi']) / (wage['wage_prev1'] / wage['cpi_prev1']) - 1.0
        dW = MRIO_df_to_vec(wage, 'REG_imp','PROD_COMM', 'd_wage', self.R_list, self.P_list)

        dK = np.nan_to_num(dK)
        dW = np.nan_to_num(dW)

        # empl_t0 =  self.common['empl_base'] * (dQ * self.params['Q_ln']) +\
            #  self.common['empl_base'] * (dK * self.params['K_ln_L1']) + \
                # self.common['empl_base'] * (dW * self.params['W_ln_L1'])

        # 2022 
        # employment at the end of 2021 == empl_base
        # 2022 employment start == empl_base + empl_base * dK * e + empl_base * dW * e
        # 2022 employment end == [2022 employment start] + [2022 employment start] * dQ * e 

        empl_t0 = self.common['empl_base'] * (dK * self.params['K_ln_L1']) + \
                self.common['empl_base'] * (dW * self.params['W_ln_L1'])
        
        return {
            'd_employment': empl_t0,
            'd_labor': empl_t0 * MRIO_df_to_vec(self.common['wage'], 'REG_imp', 'PROD_COMM', 'wage', self.R_list, self.P_list)
        }
    
    def calc_dempl(self, dq):
        # ! this is WITHIN year, i.e. K held constant, Q changes
        # because K is held constant in the within year case, therefore:
        # dQ = dq/q_base
        # effect_Q = dQ * (PARAMETERS['ln_Q']) * empl_base
        # input is a single dq vector or a dict of named dq vectors
        def _calc(vec):
            dQ = np.nan_to_num(vec / self.common['q_base'], posinf=0, neginf=0)
            return np.nan_to_num(dQ * self.params['Q_ln'] * self.common['empl_base'])

        if not isinstance(dq, dict):
            return _calc(dq)

        return {key: _calc(val) for key, val in dq.items()}
        
    def calc_dempl_perc(self, percentage_change):

        empl_d = self.common['empl_base'] * percentage_change

        return {
            'd_employment': empl_d,
            'd_labor': empl_d * MRIO_df_to_vec(self.common['wage'], 'REG_imp', 'PROD_COMM', 'wage', self.R_list, self.P_list)
        }
    
    def labour_share(self, dq_total, dempl_total, price_index, dp):

        wage = MRIO_df_to_vec(self.common['wage'], 'REG_imp', 'PROD_COMM', 'wage', self.R_list, self.P_list)
        labour_share = ((self.common['empl_base'] + dempl_total)* wage) / ((dq_total + self.common['q_base']) * (price_index * (1 + dp)))
        return labour_share