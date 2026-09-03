# -*- coding: utf-8 -*-
"""
Created on Thu Jun 29 16:55:53 2023

@author: wb582890
"""

import pandas as pd
import numpy as np
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df
import os

class gov:
    """
    This class collects the variables and parameters related to government and calculates government share in trade,
    demand and spending, and changes in demand and spending.

    Parameters
    ----------
    EXOG_VARS : class
        Class for exogenous variables.
    
    Methods
    -----------
    calc_initial_spending
        Calculates government spending based on exogenous data.
    calc_endog_spending_change
        Calculates changes in government spending endogenously.
    calc_trade_share
        Calculates the default share of the government's trade share.
    calc_gov_demand
        Calculates government demand based on spending and consumption shares.
    calc_gov_demand_change
        Calculates changes in government demand endogenously.

    """ 
    
    def __init__(self, exog_vars, scenario_data):
        self.GOV = exog_vars.GOV_BASE
        self.R = exog_vars.R
        self.P = exog_vars.P
        self.R_list = exog_vars.R['Region_acronyms'].to_list()
        
        self.rev_proportion = scenario_data.rev_proportion
        self.govt_spending = scenario_data.govt_spending

        self.revenue_shares = exog_vars.GOVERNMENT_REVENUE

        self.MRIO_df_to_vec_DEF = lambda df,name: MRIO_df_to_vec(df, 'REG_imp','PROD_COMM',name, exog_vars.R_list, exog_vars.P_list)

        self.MRIO_vec_to_df_DEF = lambda vec,name: MRIO_vec_to_df(vec, name, len(exog_vars.P), exog_vars.R)\
                .rename(columns={'target-sector':'PROD_COMM','target-country-iso3':'REG_imp'}).drop(columns=['target-country'])

        # ? ok, so what govt needs? 
        # ? we set govt consumption to be in line with general ratios, so we need:
        # ? --> last year's: [income] + [profit] + [cons] + [q for some sectors] + [gdp]

    def calc_endog_spending_change(self, prev_govt, va_prev, va, gdp_prev, gdp, hh_prev, hh, wage_prev, wage, empl_prev, empl,
                                   q_prev, q, price_index, year):
        
        # Income tax (wage x empl) and SS contrib
        comp_prev = empl_prev * wage_prev
        comp_current = empl * wage
        delta_comp = comp_current - comp_prev # current price

        delta_comp = self.MRIO_vec_to_df_DEF(comp_prev, "comp_prev").merge(self.MRIO_vec_to_df_DEF(delta_comp, "delta_comp"))
        delta_comp = delta_comp.groupby(['REG_imp']).agg({'comp_prev':'sum','delta_comp':'sum'}).reset_index()
        # income change by country; current price
        delta_comp['delta_comp'] = delta_comp['delta_comp'] / delta_comp['comp_prev']
        delta_comp = delta_comp[['REG_imp','delta_comp']]

        # Sales tax
        cons_prev = self.MRIO_df_to_vec_DEF(hh_prev.reset_index().rename(columns={'TRAD_COMM':'PROD_COMM'}), 'VIPA')
        cons_current = self.MRIO_df_to_vec_DEF(hh.reset_index().rename(columns={'TRAD_COMM':'PROD_COMM'}), 'VIPA')
        cons_current = cons_current / (1+self.MRIO_df_to_vec_DEF(price_index, 'dp'))
        delta_cons = cons_current - cons_prev # last year's prices

        delta_cons = self.MRIO_vec_to_df_DEF(cons_prev, 'cons_prev').merge(self.MRIO_vec_to_df_DEF(delta_cons, 'delta_cons'))
        delta_cons = delta_cons.groupby(['REG_imp']).agg({'cons_prev':'sum','delta_cons':'sum'}).reset_index()
        # consumption change by country; constant price
        delta_cons['delta_cons'] = delta_cons['delta_cons'] / delta_cons['cons_prev']
        delta_cons = delta_cons[['REG_imp','delta_cons']]

        # ! until here

        # Capital tax (profit)
        profit_prev = self.MRIO_df_to_vec_DEF(va_prev, 'profit')
        profit_prev[profit_prev < 0] = 0
        profit_current = self.MRIO_df_to_vec_DEF(va, 'profit')
        profit_current[profit_current < 0] = 0
        delta_profit = profit_current - profit_prev

        delta_profit = self.MRIO_vec_to_df_DEF(profit_prev, "profit_prev").merge(self.MRIO_vec_to_df_DEF(delta_profit, "delta_profit"))
        delta_profit = delta_profit.groupby(['REG_imp']).agg({'profit_prev':'sum','delta_profit':'sum'}).reset_index()
        # profit change by country; current price
        delta_profit['delta_profit'] = delta_profit['delta_profit'] / delta_profit['profit_prev']
        delta_profit = delta_profit[['REG_imp','delta_profit']]

        # Royalties (can only calculate with 120 sectors)
        # Fishing/mining/extractive sectors
        # fishing [22, 23]
        # mining [24, 40]
        if(len(self.P) != 120):
            os.system('color 4')
            print("######################################################################################")
            print("!!!! ERROR: Royalties can only be calculated with 120 sectors for now.")
            print("######################################################################################")
            print("Exiting.")
            os.system('color')
            quit() 
        q_prev = self.MRIO_vec_to_df_DEF(q_prev, 'q_prev').query("PROD_COMM > 21 & PROD_COMM < 41")
        q_curr = self.MRIO_vec_to_df_DEF(q, 'q').query("PROD_COMM > 21 & PROD_COMM < 41")
        delta_royalties = self.MRIO_df_to_vec_DEF(q_curr, 'q') * (1+self.MRIO_df_to_vec_DEF(price_index, 'dp')) - self.MRIO_df_to_vec_DEF(q_prev, 'q_prev')

        delta_royalties = q_prev.merge(self.MRIO_vec_to_df_DEF(delta_royalties, "delta_royalties"))
        delta_royalties = delta_royalties.groupby(['REG_imp']).agg({'q_prev':'sum','delta_royalties':'sum'}).reset_index()
        # royalties change by country; current price
        delta_royalties['delta_royalties'] = delta_royalties['delta_royalties'] / delta_royalties['q_prev']
        delta_royalties = delta_royalties[['REG_imp','delta_royalties']]

        # Residual - GDP based
        gdp_prev_country = gdp_prev.groupby(['REG_imp']).agg('sum').reset_index().rename(columns={'gdp':'gdp_prev'})
        gdp_country = gdp.groupby(['REG_imp']).agg('sum').reset_index()
        delta_gdp = gdp_country[['REG_imp','gdp']].merge(gdp_prev_country[['REG_imp','gdp_prev']])
        delta_gdp['delta_gdp'] = delta_gdp['gdp'] / delta_gdp['gdp_prev'] -1
        delta_gdp = delta_gdp[['REG_imp','delta_gdp']]

        # apply to existing spending
        govt = prev_govt.merge(delta_comp).merge(delta_cons).merge(delta_profit).merge(delta_royalties).merge(delta_gdp)
        govt['Income_tax_share'] = govt['Income_tax_share'] * (1 + govt['delta_comp'])
        govt['SS_contrib'] = govt['SS_contrib'] * (1 + govt['delta_comp'])
        govt['Sales_tax'] = govt['Sales_tax'] * (1 + govt['delta_cons'])
        govt['Capital_tax_share'] = govt['Capital_tax_share'] * (1 + govt['delta_profit'])
        govt['Royalties'] = govt['Royalties'] * (1 + govt['delta_royalties'])
        govt['Residual'] = govt['Residual'] * (1 + govt['delta_gdp'])

        return(govt[prev_govt.columns])

    def calc_initial_spending(self):
        # calculate initial spending linked to source
        # spending by country
        gov_spending = self.GOV.groupby('REG_imp').agg({'VIGA':'sum'}).reset_index()
        revenue_shares = pd.melt(self.revenue_shares, id_vars=['REG_imp'])
        revenue = revenue_shares.merge(gov_spending)
        revenue['VIGA'] = revenue['VIGA'] * revenue['value']
        
        revenue = revenue.pivot_table(index='REG_imp', columns='variable', values='VIGA').reset_index()

        return(revenue)
    
    def calc_trade_share(self):
        GOV = self.GOV.reset_index(drop=False)

        VIGA_prod = GOV.groupby(["REG_imp","TRAD_COMM"])["VIGA"].sum()
        VIGA_prod = VIGA_prod.to_frame()
        VIGA_prod = VIGA_prod.rename(columns={"VIGA": "VIGA_prod"})

        GOV = GOV.merge(VIGA_prod, how='left', on=["REG_imp","TRAD_COMM"])
        GOV["VIGA_tradeshare"] = GOV["VIGA"] / GOV["VIGA_prod"]

        VIGA_total = GOV.groupby(["REG_imp"])["VIGA"].sum()
        VIGA_total = VIGA_total.to_frame()
        VIGA_total = VIGA_total.rename(columns={"VIGA": "VIGA_total"})

        GOV = GOV.merge(VIGA_total, how='left', on=["REG_imp"])
        GOV["VIGA_defaultshare"] = GOV["VIGA"] / GOV["VIGA_total"]
        
        self.GOV = GOV

    def calc_gov_demand(self, government_spending_, price_index, emission_cost, new_gov_base=None):

        prices = price_index.rename(columns={'REG_imp':'REG_exp','PROD_COMM':'TRAD_COMM'})
        emission_cost_ = emission_cost.groupby(['REG_exp','TRAD_COMM','REG_imp']).agg({'emission_cost':'sum'}).reset_index()

        if new_gov_base is None:
            gov_base = self.GOV.reset_index()
        else:
            gov_base = new_gov_base.copy()
            gov_base['VIGA'] = gov_base['VIGA'] + gov_base['VIGA_dyn']
            gov_base['VIGA'] = gov_base['VIGA'].apply(lambda x: x if x > 0.0 else 0.0) 
        
        gov_base = gov_base[['REG_exp','REG_imp','TRAD_COMM','VIGA']].copy()

        consumption_shares = gov_base.merge(prices, how='left')
        consumption_shares = consumption_shares.merge(emission_cost_, how='left', on=['REG_exp','REG_imp','TRAD_COMM'])
        consumption_shares['emission_cost'] = consumption_shares['emission_cost'].fillna(0)
        consumption_shares['price_index']   = consumption_shares['price_index'].fillna(1.0)
        consumption_shares['VIGA_nominal'] = consumption_shares['VIGA'] * consumption_shares['price_index']
        _denom = consumption_shares['VIGA_nominal'].replace(0, np.nan)
        consumption_shares['emission_cost'] = (consumption_shares['emission_cost'] / _denom).fillna(0)
        consumption_shares['emission_cost'] = consumption_shares['emission_cost'].apply(lambda x: 0 if x < 0 else (3.0 if x > 3.0 else x))
        consumption_shares['price_index'] = consumption_shares['price_index'] + consumption_shares['emission_cost']
        consumption_shares['share'] = consumption_shares['VIGA'] / consumption_shares.groupby(['REG_imp'])['VIGA'].transform('sum')

        #! ITT
        # assume that constant price shares are untouched
        government_spending = consumption_shares.rename(columns={'VIGA':'VIGA_old'}).merge(government_spending_, how='left')
        government_spending['VIGA'] = government_spending['share'] * government_spending['government_spending'] # nominal spending assuming same shares
        government_spending['VIGA_const'] = government_spending['VIGA'] / government_spending['price_index']
        government_spending['VIGA_const_adj'] = government_spending['share'] * government_spending.groupby(['REG_imp'])['VIGA_const'].transform('sum')

        government_spending['VIGA'] = government_spending['VIGA_const_adj'] - government_spending['VIGA_old']
        # government spending is NOMINAL; we assume that the government is NOT price sensitive

        government_spending = government_spending.set_index(['REG_imp','REG_exp','TRAD_COMM'])[['VIGA']]
        return(government_spending)
        
    def calc_gov_demand_change(self, recyc_rev, price_index_):
        # price_index is vector
        price_index = self.MRIO_vec_to_df_DEF(price_index_, 'price_index').rename(columns={'REG_imp':'REG_exp','PROD_COMM':'TRAD_COMM'})

        GOV = self.GOV.merge(recyc_rev['recyc_govt_base'], how='left', on=['REG_imp']).fillna(0)
        GOV = GOV.merge(self.govt_spending[['REG_imp','TRAD_COMM','govt_spend']].pipe(lambda d: d[(~d['REG_imp'].isna()) & (d['REG_imp'].isin(self.R_list))]), how='left')
        GOV.fillna(0, inplace=True)

        # if no GOV consumption towards the sector in GLORIA (i.e. VIGA == 0), then assume
        # 100% domestic production
        GOV.loc[GOV['REG_exp']==0,'VIGA_tradeshare'] = 1.0
        GOV.loc[GOV['REG_exp']==0,'REG_exp'] = GOV.loc[GOV['REG_exp']==0,'REG_imp']
        GOV = GOV.merge(price_index, how='left', on=['REG_exp','TRAD_COMM'])

        GOV["delta_y_gov_default"] = (GOV["recyc_govt_base"] * GOV["VIGA_defaultshare"]) / GOV['price_index']
        # recyc_govt_base [this is the amount recycled] x govt_spend [spending share (from total) towards the sector] x VIGA_tradeshare [share of REG_exp in sectoral supply]
        GOV["delta_y_gov_user"] = (GOV["recyc_govt_base"] * GOV["govt_spend"] * GOV["VIGA_tradeshare"]) / GOV['price_index']
        
        GOV = GOV.set_index(["REG_imp", "REG_exp", "TRAD_COMM"])
        
        if self.rev_proportion["govt_spending"][0] == 0:
            dGOV = GOV.loc[:, ["delta_y_gov_user"]]
            dGOV = dGOV.rename(columns={"delta_y_gov_user": "delta_y_gov"})
        else:
            dGOV = GOV.loc[:, ["delta_y_gov_default"]]
            dGOV = dGOV.rename(columns={"delta_y_gov_default": "delta_y_gov"})
        
        self.dGOV = dGOV
        
        return self.dGOV

