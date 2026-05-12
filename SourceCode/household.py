# -*- coding: utf-8 -*-
"""
Created on Thu Jun 29 16:54:26 2023

@author: wb582890
"""

import pandas as pd
import numpy as np
import time

from SourceCode.InputOutput import IO
from SourceCode.scenario import scenario
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df

class household:
    """
    This class collects the variables and parameters related to households and calculates household prices,and changes in prices and income.

    Parameters
    ----------
    EXOG_VARS : class
        Class for exogenous variables.
    
    Methods
    -----------
    build_hh_price
        Calculates household prices.
        
    calc_hh_demand_change
        Calculates changes in household prices and income.

    """  
    def __init__(self, EXOG_VARS):
        
        self.HH = EXOG_VARS.HH_BASE

        self.multiyear = EXOG_VARS.MULTIYEAR
        
        self.cons_sec = [
            "Food_beverages_tobacco","Clothing_footwear", "Housing",
            "House_furnishing", "Medical_health", "Transport_communication",
            "Recreation", "Education", "Other"]
        self.COU_ID = EXOG_VARS.COU_ID

        self.R_list = EXOG_VARS.R_list
        self.P_list = EXOG_VARS.P_list
        self.R = EXOG_VARS.R

        # set up params
        self.params = EXOG_VARS.PARAMETERS[['REG_imp','PROD_COMM','consumption_Price_ln','consumption_Income_ln']].copy()
        self.params = self.params.rename(columns={'PROD_COMM':'TRAD_COMM'})
        self.params.columns = [x.replace("consumption_","") for x in self.params.columns]

        # read in compensation shares
        # ? we currently use compensations shares, because we only capture labour income; hence impacts need to be dampened by the 
        # ? share of labour compensation to total disposable income
        self.comp_shares = EXOG_VARS.COMPENSATION_SHARE.copy()

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v

    def build_hh_price(self, dp_pre_trade, emission_cost_hh, price_index, prev=None, year=None):
        # emission cost hh is: REG_imp | PROD_COMM == FD_1 | TRAD_COMM | REG_exp | emission_cost (nominal USDk)
        # price index is: REG_imp | PROD_COMM | price_index

        # ? HH price considers dp_pre_trade, but also includes 
        # ? direct tax on households, which is based on the emission cost, 
        # ? emission cost however is in nominal terms, so we need to consider how the price_index changes
          
        # we start with pre-trade price impacts
        dp_pre_trade = dp_pre_trade.set_index(["REG_imp","TRAD_COMM","REG_exp"])
        
        HH_elas = self.HH.reset_index().merge(dp_pre_trade, how='left', on=['REG_imp','REG_exp','TRAD_COMM'])
        # HH_elas = HH_elas.astype({'TRAD_COMM':'str'})

        # we then allocate emission costs
        emission_costs = emission_cost_hh.copy()
        emission_costs = emission_costs.groupby(['REG_imp','REG_exp','TRAD_COMM']).agg({'emission_cost':'sum'}).reset_index()

        if prev is not None:
            emission_costs_prev = prev.copy()
            
            emission_costs_prev = emission_costs_prev.groupby(['REG_imp','REG_exp','TRAD_COMM']).agg({'emission_cost':'sum'}).reset_index()
            emission_costs_prev = emission_costs_prev.rename(columns={'emission_cost':'emission_cost_prev'})

            emission_costs = emission_costs.merge(emission_costs_prev, how='left', on=['REG_imp','REG_exp','TRAD_COMM'])
            emission_costs['emission_cost'] = emission_costs['emission_cost'] - emission_costs['emission_cost_prev']
            emission_costs = emission_costs.drop(columns=['emission_cost_prev'])
        
        HH_elas = HH_elas.merge(emission_costs, how='left', on=['REG_imp','REG_exp','TRAD_COMM']).fillna(0)

        # and nominal price indices
        price_index_ = price_index.copy()
        # .astype({'PROD_COMM':'str'})
        HH_elas = HH_elas.merge(price_index_.rename(columns={'REG_imp':'REG_exp','PROD_COMM':'TRAD_COMM'}), how='left', on=['REG_exp','TRAD_COMM'])
        # then calculate tax price hike
        HH_elas['VIPA_nominal'] = HH_elas['VIPA'] * HH_elas['price_index']
        HH_elas['delta_tax_hh'] = np.nan_to_num(HH_elas['emission_cost'] / HH_elas['VIPA_nominal'], nan=0)
        # limit to max 0-300%
        HH_elas['delta_tax_hh'] = HH_elas['delta_tax_hh'].apply(lambda x: (0 if x < 0 else (3.0 if x > 3.0 else x)))

        # ? this comes on top of other price effects! 
        # ? so dp_pre_trade + delta_tax_hh together gives consumer price
        # ? we get the weighted average price change for consumers across all
        # import pdb; pdb.set_trace()

        HH_elas['delta_p_avg'] = HH_elas['VIPA_nominal'] / HH_elas.groupby(['REG_imp','TRAD_COMM'])['VIPA_nominal'].transform('sum')
        HH_elas['delta_p_avg'] = HH_elas['delta_p_avg'] * (HH_elas['delta_tax_hh'] + HH_elas['delta_p'])

        VIPA_prod = HH_elas.groupby(["REG_imp","TRAD_COMM"]).agg({'VIPA':'sum','delta_p_avg':'sum'}).reset_index()
        VIPA_prod = VIPA_prod.rename(columns={"VIPA": "VIPA_prod"})

        HH_price = VIPA_prod[['REG_imp','TRAD_COMM','delta_p_avg','VIPA_prod']]

        #? output is: HH_price: REG_imp | TRAD_COMM | delta_p_avg | VIPA_prod

        return HH_price
        
    def calc_hh_demand_change(self, HH_price_, recyc_rev, inc_exog, inc_exog_prev, dlabor_inc_nat=None, year=None):
        #? inc_exog is: REG_imp | dlabor_exog

        HH_price = HH_price_.copy()
        HH_price = HH_price.merge(self.params, how='left')
        HH_price = HH_price[['REG_imp','TRAD_COMM','VIPA_prod','delta_p_avg','Price_ln','Income_ln']]
        
        # ? dlabor is nominal compensation change
        recyc_rev_col = recyc_rev[["recyc_inc_base"]].reset_index()
        if type(dlabor_inc_nat) == pd.DataFrame:
            HH_price = HH_price.merge(dlabor_inc_nat[["dlabor"]].reset_index(), how='left', on=["REG_imp"])
            HH_price = HH_price.merge(recyc_rev_col, how='left', on=["REG_imp"])
            HH_price = HH_price.merge(inc_exog_prev.rename(columns={'dlabor_exog':'prev_dlabor_exog'}), how='left', on=['REG_imp'])
            HH_price = HH_price.merge(inc_exog, how='left', on=['REG_imp'])
            HH_price = HH_price.fillna(0)
            HH_price["recyc_inc_base"] = HH_price["recyc_inc_base"] + HH_price["dlabor"] + HH_price['dlabor_exog'] - HH_price["prev_dlabor_exog"]
            HH_price = HH_price.drop(columns=["dlabor","dlabor_exog","prev_dlabor_exog"])
        else:
            HH_price = HH_price.merge(recyc_rev_col, how='left', on=["REG_imp"])
            HH_price = HH_price.merge(inc_exog_prev.rename(columns={'dlabor_exog':'prev_dlabor_exog'}), how='left', on=['REG_imp'])
            HH_price = HH_price.merge(inc_exog, how='left', on=['REG_imp'])
            HH_price = HH_price.fillna(0)
            HH_price["recyc_inc_base"] = HH_price["recyc_inc_base"] + HH_price['dlabor_exog'] - HH_price["prev_dlabor_exog"]
            HH_price = HH_price.drop(columns=["dlabor_exog","prev_dlabor_exog"])

        HH_price = HH_price.rename(columns={'recyc_inc_base':'delta_inc'}).fillna(0)

        # if year == 2021:
            # import pdb; pdb.set_trace()

        # ? ok, so here recyc_inv is the total nominal(!) income growth; we need to know what was income before
        # ? note: CONSUMPTION <> INCOME, so cannot just sum(VIPA)

        empl_base = self.common['employment_base'].merge(self.common['wage_base'])
        empl_base['compensation'] = empl_base['employment_base'] * empl_base['wage']
        empl_base = empl_base.groupby(['REG_imp']).agg({'compensation':'sum'}).reset_index()

        HH_price = HH_price.merge(empl_base, how='left', on=['REG_imp'])
        HH_price = HH_price.merge(self.common['cpi'], how='left', on=['REG_imp'])
        
        # ? income change; but delta_inc is nominal; VIPA_nat is real
        # ? real income change needs to consider price levels
        HH_price['quasi_CPI'] = (HH_price['VIPA_prod'] / HH_price.groupby(['REG_imp'])['VIPA_prod'].transform('sum')) * HH_price['delta_p_avg']
        HH_price['quasi_CPI'] = HH_price.groupby(['REG_imp'])['quasi_CPI'].transform('sum')
        HH_price = HH_price.merge(self.comp_shares, how='left', on=['REG_imp'])
        HH_price["delta_inc_rel"] = (HH_price["delta_inc"] / (HH_price['cpi'] + HH_price['quasi_CPI'])) / ((HH_price["compensation"] / HH_price['share_compensation_in_gross_disposable_income']) / (HH_price['cpi']))
        # apply elasticities
        HH_price["VIPA_inc_eff"] = HH_price['VIPA_prod'] * HH_price["delta_inc_rel"] * HH_price["Income_ln"]
        HH_price["VIPA_op_eff"] = HH_price['VIPA_prod'] * HH_price["delta_p_avg"] * HH_price["Price_ln"]

        HH_price_store = HH_price.copy()
        HH_price = HH_price[['REG_imp','TRAD_COMM','VIPA_inc_eff','VIPA_op_eff','VIPA_prod']].copy()

        # so this is real change
        
        # calculation of VIPA after price change
        dHH = self.HH.reset_index("REG_exp", drop=False)
        dHH = dHH.merge(HH_price, how='left', on=["REG_imp","TRAD_COMM"])

        # Compute new demands assuming constant product and origin country structure
        dHH["delta_y_price"] = dHH["VIPA_op_eff"] * dHH["VIPA"] / dHH["VIPA_prod"]
        dHH["delta_y_inc"] = dHH["VIPA_inc_eff"] * dHH["VIPA"] / dHH["VIPA_prod"]
        
        # add exog
        hh_exog = self.common['hh_exog'].copy().rename(columns={'dy':'dy_exog'})
        hh_exog['TRAD_COMM'] = hh_exog['TRAD_COMM'].astype('int16')
        dHH = dHH.merge(hh_exog, how='left', on=['REG_imp','TRAD_COMM','REG_exp'])

        # TODO need to consider save_rate; need new total income and new total consumption
        dcalc = HH_price_store.copy().groupby(['REG_imp']).agg({'delta_inc':'mean','compensation':'mean','cpi':'mean','quasi_CPI':'mean'}).reset_index()
        dcalc['real_income'] = (dcalc["delta_inc"] + dcalc["compensation"]) / (dcalc['cpi'] + dcalc['quasi_CPI'])
        dcalc = dcalc.groupby(['REG_imp']).agg({'real_income':'sum'}).reset_index()
        dcalc = dcalc.merge(dHH.groupby(['REG_imp']).agg({'VIPA':'sum','delta_y_price':'sum','delta_y_inc':'sum','dy_exog':'sum'}).reset_index(), how='left', on=['REG_imp'])
        dcalc['real_spend'] = dcalc['VIPA'] + dcalc['delta_y_price'] + dcalc['delta_y_inc'] + dcalc['dy_exog']

        # if year == 2035:
            # import pdb; pdb.set_trace()

        dcalc['endog_save'] = 1 - dcalc['real_spend']/dcalc['real_income']

        # ? save rate is calculate from last 3 period
        save_rate = self.common['save_rate1'].rename(columns={'save_rate':'save_rate1'})\
            .merge(self.common['save_rate2'].rename(columns={'save_rate':'save_rate2'}), how='left', on='REG_imp')\
                .merge(self.common['save_rate3'].rename(columns={'save_rate':'save_rate3'}), how='left', on='REG_imp')
        save_rate['save_rate'] = (save_rate['save_rate1'] + save_rate['save_rate2'] + save_rate['save_rate3']) / 3.0
        save_rate = save_rate[['REG_imp','save_rate']].copy()

        dcalc = dcalc[['REG_imp','endog_save','real_income']].merge(save_rate, how='left', on='REG_imp')
        dcalc['windfall_save'] = (dcalc['endog_save'] - dcalc['save_rate']) # as percentage of real income
        dcalc.loc[dcalc['windfall_save']<0, 'windfall_save'] = 0.0

        # TODO specify better lambda_save = 0.1
        lambda_save = 0.1
        dcalc['windfall_spend'] = dcalc['windfall_save'] * lambda_save
        dcalc = dcalc[['REG_imp','windfall_spend']].copy()

        HH_price_store = HH_price_store.merge(dcalc, how='left', on='REG_imp')
        HH_price_store['VIPA_save_eff'] = HH_price_store['VIPA_prod'] * HH_price_store['windfall_spend'] * HH_price_store['Income_ln']
        HH_price_store = HH_price_store[['REG_imp','TRAD_COMM','VIPA_inc_eff','VIPA_op_eff','VIPA_save_eff','VIPA_prod']].copy()

        dHH = self.HH.reset_index("REG_exp", drop=False)
        dHH = dHH.merge(HH_price_store, how='left', on=["REG_imp","TRAD_COMM"])

        # Compute new demands assuming constant product and origin country structure
        dHH["delta_y_price"] = dHH["VIPA_op_eff"] * dHH["VIPA"] / dHH["VIPA_prod"]
        dHH["delta_y_inc"] = dHH["VIPA_inc_eff"] * dHH["VIPA"] / dHH["VIPA_prod"]
        dHH["delta_y_save"] = dHH["VIPA_save_eff"].astype("float64") * dHH["VIPA"] / dHH["VIPA_prod"]
        
        dHH = dHH.set_index(['REG_imp', 'REG_exp', 'TRAD_COMM'])
        
        # TODO return savings
        self.dHH_price = dHH.loc[:, ["delta_y_price"]]
        self.dHH_inc = dHH.loc[:, ["delta_y_inc"]]
        self.dHH_save = dHH.loc[:, ["delta_y_save"]]

        return self.dHH_price, self.dHH_inc, self.dHH_save
    
