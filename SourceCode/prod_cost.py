# -*- coding: utf-8 -*-
"""
Created on Thu Jun 29 16:53:55 2023

@author: wb582890
"""

import pandas as pd
import numpy as np
from SourceCode.utils import MRIO_df_to_vec

class prod_cost:
    def __init__(self, EXOG_VARS, scenario):
        self.LABOR_BASE = EXOG_VARS.LABOR_BASE
        self.INITIAL_VA = EXOG_VARS.INITIAL_VA.query("year == 2019").drop(columns=['year'])
        self.output = EXOG_VARS.output
        self.R = EXOG_VARS.R
        self.P = EXOG_VARS.P
        self.R_list = EXOG_VARS.R_list
        self.P_list = EXOG_VARS.P_list
        
        self.rev_proportion = scenario.rev_proportion

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v
        
    def prod_cost_impact(self, cost_shock):

        # relative
        cost_shock_ = cost_shock[cost_shock['Type'].str.contains("rel")].copy()

        cost_shock_ = cost_shock_.astype({'PROD_COMM':'int16'})
        cost_shock_['Value'] = cost_shock_['Value'].fillna(0)
        
        return cost_shock_
    
    def calc_prod_cost_impact(self, cost_shock, dq=None, dp=None):
        # q_base and price_index are present, both as df
        q_base = self.common['q_base'].merge(self.common['price_index'])
        q_base['q_nominal'] = q_base['q_base'] * q_base['price_index']
        q_nominal = MRIO_df_to_vec(q_base, 'REG_imp','PROD_COMM','q_nominal', self.R_list, self.P_list)

        p_impact = np.nan_to_num(cost_shock / q_nominal, nan=0, posinf=0.0, neginf=0.0)
        return(p_impact)

    def calc_initial(self):
        # employment and wages
        VA = self.INITIAL_VA.copy()

        # get compensation
        compensation = VA[['REG_imp','PROD_COMM','compensation']].rename(columns={'compensation':'labor'})

        self.labor_comp = compensation.set_index(['REG_imp','PROD_COMM'])
        
    def calc_labor_cost_impact(self, price_index, q_base, dlabor_sec, dq_total=None, dp_new=None):
        # dlabor_sec is compensation change; nominal price

        # given change in sectoral wages and employment we calculate price changes
        # dlabor_sec is [REG_imp | PROD_COMM | dlabor_x]
        # exog_prod_cost is [REG_imp | PROD_COMM | prod_cost_rel]
        # self.output is [REG_imp | PROD_COMM | output]
        dlabor_sec = dlabor_sec.copy()
        dlabor_sec.columns = ['REG_imp','PROD_COMM','dlabor']

        if dq_total is not None:
            q_base = q_base.merge(dq_total, how='left', on=['REG_imp','PROD_COMM'])
            q_base['q_base'] = q_base['q_base'] + q_base['dq_total']

        if dp_new is not None:
            price_index = price_index.merge(dp_new, how='left', on=['REG_imp','PROD_COMM'])
            price_index['price_index'] = price_index['price_index'] * (1 + price_index['dp_new'])

        wage_impact = q_base.merge(dlabor_sec, 'left').merge(price_index, how='left', on=['REG_imp','PROD_COMM'])
        wage_impact['d_cost'] = np.nan_to_num(wage_impact['dlabor'] / (wage_impact['q_base'] * wage_impact['price_index']), nan=0, posinf=0, neginf=0)

        wage_impact = wage_impact[['REG_imp','PROD_COMM','d_cost']].rename(columns={'d_cost':'prod_cost_rel'})

        return wage_impact

    def calc_prod_cost(self, tax_rev_prod, recyc_rev):
        # TODO does not consider changes in labor cost!!, currently done in above function, might consolidate

        # ? so tax_rev_prod is the tax revenue per producer (this is nominal dollars)
        # ? recyc_rev is the economy level recycled reveneus (nominal dollars too)
        # ? revenue recycling options are
        # ? --> recyc_govt_base ---> govt spending
        # ? --> recyc_inc_base ---> income tax
        # ? --> recyc_payr_base ---> payroll tax
        # ? --> recyc_inv_base ---> govt investment

        # ? --> here we want to consider only those that impact production costs; 
        # ? so we increase prices in line with tax-revenues and decrease them with payroll-tax

        self.tax_rev_prod = tax_rev_prod

        # this is tax paid by industry by industry; nominal USDk
        tax_rev_prod = tax_rev_prod.reset_index()

        # this is many spent on decreasing payroll tax (socsec); nominal USDk
        payroll_impact = recyc_rev[['recyc_payr_base']].reset_index()

        # this is compensation (nominal) USDk
        compensation = self.labor_comp.reset_index()
        compensation['share'] = compensation['labor'] / compensation.groupby(['REG_imp'])['labor'].transform('sum')
        compensation['share'].fillna(0, inplace=True)
        compensation = compensation[['REG_imp','PROD_COMM','share']].copy()

        # payroll impact is NOT targeted
        payroll_impact = compensation.merge(payroll_impact, how='left', on=['REG_imp'])
        payroll_impact['recyc_payr_impact'] = payroll_impact['share'] * payroll_impact['recyc_payr_base']
        payroll_impact = payroll_impact[['REG_imp','PROD_COMM','recyc_payr_impact']].copy()
        
        # bring together with taxes paid
        tax_impact = payroll_impact.merge(tax_rev_prod, how='left', on=['REG_imp','PROD_COMM'])
        tax_impact['tax_impact'] = tax_impact['recyc_payr_impact'] - tax_impact['tax_rev_prod_base']

        # get output, but it's constant, so convert to nominal
        q_base = self.common['q_base'].merge(self.common['price_index'], how='left')
        q_base['q_nominal'] = q_base['q_base'] * q_base['price_index']
        q_base = q_base[['REG_imp','PROD_COMM','q_nominal']]
        tax_impact = q_base.merge(tax_impact.drop(columns=['recyc_payr_impact','tax_rev_prod_base']), how='left', on=['REG_imp','PROD_COMM'])

        # calc percentage impact
        tax_impact['prod_cost_rel'] = (1+tax_impact['tax_impact'] / tax_impact['q_nominal'])
        tax_impact['prod_cost_rel'].fillna(1, inplace=True)
        tax_impact = tax_impact[['REG_imp','PROD_COMM','prod_cost_rel']].copy()

        self.exog_prod_cost = tax_impact
        
        # Return the computed production costs
        return self.exog_prod_cost

