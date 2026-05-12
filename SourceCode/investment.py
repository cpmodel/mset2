# -*- coding: utf-8 -*-
"""
Created on Fri Jun 23 15:51:43 2023

@author: meime
"""

import numpy as np
import pandas as pd
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df

class invest:
    """
    This class collects the variables and parameters related to investment and calculates investment shares,
    induced investment, recycled investment, and exogenous investment.

    Parameters
    ----------
    EXOG_VARS : class
        Class for exogenous variables.
    INV_CONV : DataFrame
        Investment converter.
    scenario : class
        Class for scenario assumptions.
    year : int
        Year of the simulation.
    
    
    Methods
    -----------
    calc_inv_share
        Calculates fixed capital formation share relative to exports by region.
    calc_dy_inv_induced
        Calculates induced investment.
    calc_dy_inv_recyc
        Calculates investment from revenue recycling.
    calc_dy_inv_exog
        Disaggregates exogenous investment.

    Output:
    - inv_output: DataFrame containing investment output data
    - inv_conv: DataFrame containing investment conversion data
    - y_fcf_prop: DataFrame containing investment-propensity-adjusted input-output data

    """ 

    def __init__(self, EXOG_VARS, INV_CONV, scenario, year):
        self.IO_PATH = EXOG_VARS.IO_PATH
        
        self.FCF = EXOG_VARS.FCF_BASE

        self.REGIONS = EXOG_VARS.R
        self.PRODUCTS = EXOG_VARS.P
        self.REGIONS_list = EXOG_VARS.COU_ID

        self.MULTIYEAR = EXOG_VARS.MULTIYEAR

        # this is now by country such as
        # investor_country | investment_by | inv_good | value
        # columns wise == 1; ie groupby(REG_imp.PROD_COMM) sum should be 1.0
        self.INV_CONV = INV_CONV
        
        self.output = EXOG_VARS.output
        self.inv_spending = scenario.inv_spending
        self.rev_proportion = scenario.rev_proportion

        self.investment_induced = pd.DataFrame(columns=['REG_imp','PROD_COMM','dk'])
        self.investment_recyc = pd.DataFrame(columns=['REG_imp','PROD_COMM','dk'])
        self.investment_exog = pd.DataFrame(columns=['REG_imp','PROD_COMM','dk'])

        # load the following:
        # q_base, capital_stock, PARAMETERS
        self.R_list = EXOG_VARS.R_list
        self.P_list = EXOG_VARS.P_list

        self.MRIO_df_to_vec_DEF = lambda df,name: MRIO_df_to_vec(df, 'REG_imp','PROD_COMM',name, EXOG_VARS.R_list, EXOG_VARS.P_list)

        self.MRIO_vec_to_df_DEF = lambda vec,name: MRIO_vec_to_df(vec, name, len(EXOG_VARS.P), EXOG_VARS.R)\
                .rename(columns={'target-sector':'PROD_COMM','target-country-iso3':'REG_imp'}).drop(columns=['target-country'])

        # set up params
        load_param = lambda var_: MRIO_df_to_vec(EXOG_VARS.PARAMETERS,'REG_imp','PROD_COMM', var_ ,self.R_list,self.P_list)

        self.params = {}
        self.params['int_rate'] = load_param('investment_int_rate_L1')
        self.params['GDP_ln_L1'] = load_param('investment_GDP_ln_L1')
        self.params['utilisation_rate_ln_L1'] = load_param('investment_dev_normaloutput_L1') # might change later, not the same as elsewhere

        # set up params
        self.params = EXOG_VARS.PARAMETERS[['REG_imp','PROD_COMM','investment_int_rate_L1','investment_GDP_ln_L1','investment_dev_normaloutput_L1']].copy()
        self.params.columns = [x.replace("investment_","") for x in self.params.columns]

        # get inflation target
        self.YEAR = year
        self.INFLATION_TARGET = EXOG_VARS.INFLATION_TARGET[['REG_imp',str(self.YEAR-1),str(self.YEAR)]].rename(columns={str(self.YEAR-1):'inflation_target_prev',
                                                                                                                        str(self.YEAR):'inflation_target'})

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v
        
    # def adjust_INV_CONV_AGRI(self):        
    #     # REG_imp | PROD_COMM | TRAD_COMM | input_coeff
    #     # columns wise == 1; ie groupby(REG_imp.PROD_COMM) sum should be 1.0
    #     agri_output = self.output[self.output['PROD_COMM'].isin(np.arange(1,24).tolist())].copy()
        
    #     # calculate output shares
    #     agri_output['share'] = agri_output['output'] / agri_output.groupby(['REG_imp',"PROD_COMM"])["output"].transform('sum')

    #     # assign to investment shares
    #     agri_output = agri_output.astype({'PROD_COMM':'str'})
    #     INV_CONV = self.INV_CONV.merge(agri_output.rename(columns={'PROD_COMM':'TRAD_COMM'}),
    #                                     how='left', on=['REG_imp','TRAD_COMM'])
        
    #     sel = INV_CONV['share'].isna()
    #     # treat agri sectors
    #     INV_CONV.loc[~sel, 'input_coeff'] = INV_CONV[~sel]['share'] * INV_CONV[~sel].groupby(['REG_imp','PROD_COMM'])['input_coeff'].transform('sum')

    #     INV_CONV = INV_CONV.drop(columns=['share', 'output'])

    #     self.INV_CONV = INV_CONV
        
    def calc_inv_share(self):
        FCF = self.FCF.reset_index()

        FCF['FCF_total'] = FCF.groupby(['REG_imp','TRAD_COMM'])['VDFA'].transform('sum')
        FCF['FCF_share'] = FCF['VDFA'] / FCF['FCF_total']

        self.fcf_share = FCF

        # ? fcf_share has dimensions of: | TRAD_COMM | REG_imp | FCF_share (value)
        # ? FCF_share is FCF/FCF_total
        # ? FCF_total is FCF aggregated with groupby(TRAD_COMM, REG_imp), meaning
        # ? summed across REG_exp and PROD_COMM
        # ? so FCF_total captures investment goods of a certain type (TRAD_COMM)
        # ? being demanded in an economy (REG_imp), disregarding geo origin (REG_exp)
        # ? (not there is no PROD_COMM in FD)
        # ? this means that FCF_shares tells us how much belongs to a certain
        # ? REG_exp from what is demanded in a REG_impXTRAD_COMM
        
    def calc_dy_inv_induced(self, first):

        # ! Taylor-rule, this should not be here probably
        # i = pi + r* + a1(pi - pi*) + a2*output gap
        # using Taylor (1993) a1=a2=0.5
        # need: GDP deflator; target rate of inflation; natural interest rate; output gap
        # assume long-run natural rate: 0.5%
        # inflation target: 3%

        # Output GAP
        # this is all in constant value
        normal_output = self.common['normal_output'].merge(self.common['q_base'])\
            .merge(self.common['normal_output_prev1'].rename(columns={'normal_output':'normal_output_prev1'})).merge(self.common['q_base_prev1'])
        
        output_gap = normal_output.drop(columns=['PROD_COMM']).groupby(['REG_imp']).agg('sum').reset_index()
        output_gap['output_gap'] = (output_gap['q_base'] - output_gap['normal_output']) / output_gap['normal_output'] 
        output_gap['output_gap_prev'] = (output_gap['q_base_prev1'] - output_gap['normal_output_prev1']) / output_gap['normal_output_prev1']
        output_gap = output_gap[['REG_imp','output_gap','output_gap_prev']].copy()

        # GDP
        gdp_real = self.common['gdp_real'].merge(self.common['gdp_real_prev'].rename(columns={'gdp':'gdp_prev'}))
        gdp_real = gdp_real.groupby(['REG_imp']).agg('sum').reset_index().drop(columns=['PROD_COMM'])

        # ? is GDP is current, but it's ok to do gdp/dp as we basically back calculate to last year's prices
        gdp_real['delta_gdp'] = gdp_real['gdp'] / gdp_real['gdp_prev']
        # gdp['delta_gdp'] = (gdp['gdp']) / gdp['gdp_prev']

        # ! this is CURRENT price
        gdp = self.common['va_prev1'].groupby(['REG_imp']).agg('sum').reset_index().drop(columns=['PROD_COMM'])
        gdp = gdp.set_index('REG_imp').sum(axis=1).reset_index().rename(columns={0:'gdp'})
        gdp_prev = self.common['va_prev2'].groupby(['REG_imp']).agg('sum').reset_index().drop(columns=['PROD_COMM'])
        gdp_prev = gdp_prev.set_index('REG_imp').sum(axis=1).reset_index().rename(columns={0:'gdp_prev'})

        # this year
        # dp is JUST price change (NOT INDEX)
        gdp_deflator = gdp.merge(gdp_prev).merge(self.common['dp_prev1'].rename(columns={'dp':'dp_prev1'}))
        gdp_deflator = gdp_deflator.merge(self.common['dp_prev2'].rename(columns={'dp':'dp_prev2'}))

        gdp_deflator['share'] = gdp_deflator['gdp'] / gdp_deflator.groupby(['REG_imp'])['gdp'].transform('sum')
        gdp_deflator['share_prev'] = gdp_deflator['gdp_prev'] / gdp_deflator.groupby(['REG_imp'])['gdp_prev'].transform('sum')
        gdp_deflator['dp_prev1'] = gdp_deflator['share'] * gdp_deflator['dp_prev1']
        gdp_deflator['dp_prev2'] = gdp_deflator['share_prev'] * gdp_deflator['dp_prev2']

        gdp_deflator = gdp_deflator.drop(columns=['share','PROD_COMM']).groupby(['REG_imp']).agg({'dp_prev1':'sum','dp_prev2':'sum'}).reset_index()
        gdp_deflator = gdp_deflator[['REG_imp','dp_prev1','dp_prev2']].copy()

        interest_rate = output_gap.merge(gdp_deflator)
        interest_rate = interest_rate.merge(self.INFLATION_TARGET, how='left', on=['REG_imp'])
        
        # interest_rate = 0.05 + 0.5 * [diff from inflation target] + 0.5 * [output gap]
        interest_rate['interest_rate'] = 0.005 + 0.5 * (interest_rate['dp_prev1'] - interest_rate['inflation_target']) + 0.5 * (interest_rate['output_gap'])
        interest_rate['interest_rate_real'] = (interest_rate['interest_rate'] - interest_rate['dp_prev1']) / (1 + interest_rate['dp_prev2']) # 0.02 is 2%

        interest_rate['interest_rate_prev'] = 0.005 + 0.5 * (interest_rate['dp_prev2'] - interest_rate['inflation_target_prev']) + 0.5 * (interest_rate['output_gap_prev'])
        interest_rate['interest_rate_real_prev'] = (interest_rate['interest_rate_prev'] - interest_rate['dp_prev2']) / (1 + interest_rate['dp_prev2']) # 0.02 is 2%
        interest_rate['delta_interest_rate_real'] = interest_rate['interest_rate_real'] - interest_rate['interest_rate_real_prev']

        # utilisation
        utilisation = normal_output.copy()
        utilisation['utilisation_rate'] = utilisation['q_base'] / utilisation['normal_output']
        utilisation['utilisation_rate_prev'] = utilisation['q_base_prev1'] / utilisation['normal_output_prev1']
        utilisation['delta_utilisation'] = utilisation['utilisation_rate'] / utilisation['utilisation_rate_prev']

        # apply econometric parameters
        investment = utilisation[['REG_imp','PROD_COMM','delta_utilisation']].merge(gdp_real[['REG_imp','delta_gdp']])\
            .merge(interest_rate[['REG_imp','delta_interest_rate_real']])
        investment = investment.merge(self.common['dk_base'], how='outer').fillna(1000)

        investment = investment.merge(self.params, how='left', on=['REG_imp','PROD_COMM'])

        investment['dk'] = investment['dk_base'] * (investment['delta_gdp'] - 1.0) * investment['GDP_ln_L1']
        investment['dk'] += investment['dk_base'] * (investment['delta_utilisation'] - 1.0) * investment['dev_normaloutput_L1']
        investment['dk'] += investment['dk_base'] * (investment['delta_interest_rate_real']) * investment['int_rate_L1']

        # ! limit; we need this for sectors that go into zero and then back
        investment.loc[investment['dk'] > investment['dk_base'] * 3, 'dk'] = investment['dk_base'] * 3 
        investment.loc[investment['dk'] + investment['dk_base'] < investment['dk_base'] * 0.1, 'dk'] = investment['dk_base'] * 0.1 

        # ? new INV_CONV is: REG_imp | PROD_COMM | TRAD_COMM | input_coeff
        INV_CONV = self.INV_CONV.astype({'PROD_COMM':'int16','TRAD_COMM':'int16'})
        fcf = investment[['REG_imp','PROD_COMM','dk']].merge(INV_CONV).fillna(0)
        fcf['dk'] = fcf['dk'] * fcf['input_coeff']

        fcf = fcf.rename(columns={'dk':'dy'})
        # dy now is DEMAND FOR INVESTMENT GOOD in sector [TRAD_COMM] from PROD_COMM
        # ? dy_fcf_prd: REG_imp | PROD_COMM | TRAD_COMM | input_coeff | dy
        # ? we still need to allocate to REG_exp by fcf_share
        
        # ? fcf_share is merged on dy_fcf_prd, on TRAD_COMM and REG_imp
        # ? fcf_share tells us the share of a single REG_exp in a
        # ? REG_impXTRAD_COMM pair, so with this we re-allocate
        # ? investment goods to the original trade structure
        FCF_ind = self.fcf_share.merge(fcf, how="left", on=["TRAD_COMM","REG_imp"])
        FCF_ind["dy"] = FCF_ind["FCF_share"] * FCF_ind["dy"]

        vars_ = ['REG_imp','PROD_COMM','REG_exp','TRAD_COMM']
        self.investment_induced = FCF_ind[vars_ + ['dy']].groupby(vars_).agg({'dy':'sum'}).reset_index()

        FCF_ind = FCF_ind.groupby(['REG_exp','TRAD_COMM','REG_imp']).agg({'dy':'sum'}).reset_index()
        
        self.dy_inv_induced = FCF_ind.fillna(0)

        other_country_summary_vars = interest_rate[['REG_imp','interest_rate','interest_rate_real','dp_prev1','output_gap']].rename(columns={'dp_prev1':'gdp_deflator'})

        if first:
            initial_rates = self.common['initial_rates']
            initial_rates['nominal_interest_rate'] = initial_rates['nominal_interest_rate'] / 100 
            other_country_summary_vars = other_country_summary_vars.merge(initial_rates, how='left', on='REG_imp')

            adjustment_factor = other_country_summary_vars[['REG_imp','nominal_interest_rate','interest_rate']].copy()
            adjustment_factor['adjust'] = adjustment_factor['nominal_interest_rate'] - adjustment_factor['interest_rate']
            adjustment_factor = adjustment_factor[['REG_imp','adjust']]

            other_country_summary_vars['interest_rate_real'] = other_country_summary_vars['nominal_interest_rate'] - (other_country_summary_vars['interest_rate'] - other_country_summary_vars['interest_rate_real'])        
            other_country_summary_vars['interest_rate'] = other_country_summary_vars['nominal_interest_rate'] 
            self.other_country_summary_vars = other_country_summary_vars.drop(columns=['nominal_interest_rate'])
        else:
            adjustment_factor = self.common['interest_rate_adjust']
            other_country_summary_vars = other_country_summary_vars.merge(adjustment_factor, how='left', on='REG_imp')
            
            other_country_summary_vars['interest_rate_real'] = other_country_summary_vars['interest_rate_real'] + other_country_summary_vars['adjust']        
            other_country_summary_vars['interest_rate'] = other_country_summary_vars['interest_rate'] + other_country_summary_vars['adjust']
            self.other_country_summary_vars = other_country_summary_vars.drop(columns=['adjust'])
            
        if first: 
            return adjustment_factor
        else:
            return True

    def calc_dy_inv_recyc(self, recyc_rev, price_index_):
        # price_index is vector
        price_index = self.MRIO_vec_to_df_DEF(price_index_, 'price_index').rename(columns={"REG_imp":'REG_exp','PROD_COMM':'TRAD_COMM'})

        recyc_inv = recyc_rev.loc[:,"recyc_inv_base"]

        if len(recyc_inv) > 0:

            if self.rev_proportion['govt_investment'][0] == 1:
                base_invest = self.common['dk_base']
                base_invest['share'] = base_invest['dk_base'] / base_invest.groupby(['REG_imp'])['dk_base'].transform('sum')

                recyc_inv = base_invest.merge(recyc_inv.reset_index())
                recyc_inv['dk'] = recyc_inv['share'] * recyc_inv['recyc_inv_base']
            else:
                recyc_inv = self.inv_spending[['REG_imp','PROD_COMM','inv_spend']].merge(recyc_inv, how='left', on=["REG_imp"])   
                recyc_inv["dk"] = recyc_inv["inv_spend"] * recyc_inv["recyc_inv_base"]
            recyc_inv = recyc_inv[['REG_imp','PROD_COMM','dk']].copy()

            # ! dk here is NOMINAL USD

            # self.INV_CONV is 120x120
            # sum(column) = 1
            # REG_imp | PROD_COMM | TRAD_COMM | input_coeff
            inv_conv = self.INV_CONV
            inv_conv = inv_conv.astype({'PROD_COMM':'int16'})
            
            recyc_inv = recyc_inv.merge(inv_conv, how='left', on=['PROD_COMM','REG_imp'])
            recyc_inv['dk'] = recyc_inv['dk'] * recyc_inv['input_coeff']
            self.investment_recyc = recyc_inv[['REG_imp','PROD_COMM','TRAD_COMM','dk']].copy()
            # ? this leads to
            # ? REG_imp | PROD_COMM | investment_good | dk | input_coef
            recyc_inv = recyc_inv.drop(columns=['input_coeff'])
            recyc_inv = recyc_inv[~recyc_inv['TRAD_COMM'].isna()]

            # ? disaggregate across export partners (incl. domestic)
            fcf_share = self.fcf_share[['REG_exp','TRAD_COMM','REG_imp','FCF_share']]
            recyc_inv = recyc_inv.astype({'TRAD_COMM':'int'})
            recyc_inv = recyc_inv.merge(fcf_share, how='inner', on=['TRAD_COMM','REG_imp'])
            # ? REG_imp | REG_exp | PROD_COMM | investment_good | dk | FCF_share

            # ! convert to constant
            recyc_inv = recyc_inv.merge(price_index, how='left', on=['REG_exp','TRAD_COMM'])

            recyc_inv['dy'] = (recyc_inv['dk'] * recyc_inv['FCF_share']) / recyc_inv['price_index']
            # TODO this needs to feed back to results --> (i.e. investment recyc up)
            recyc_inv = recyc_inv.drop(columns=['FCF_share','dk','price_index']).fillna(0)

            recyc_inv = recyc_inv.groupby(['REG_imp','REG_exp','TRAD_COMM']).agg({'dy':'sum'}).reset_index()

            self.dy_inv_recyc = recyc_inv
        
        else:
            self.dy_inv_recyc = pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','dy'])
            
    def calc_dy_inv_exog(self, exog_inv:pd.DataFrame):
        # ? exog_inv has dimensions of
        # ? REG_imp | PROD_COMM | dk
        exog_inv = exog_inv.loc[:,["REG_imp","PROD_COMM","dk"]]
        exog_inv["PROD_COMM"] = exog_inv['PROD_COMM'].astype(str)

        if True:
            # self.INV_CONV is 120x120
            # sum(column) = 1
            inv_conv = self.INV_CONV

            # ! PROD_COMM -> investment by
            # ! TRAD_COMM -> investment goods sector

            exog_inv = exog_inv.merge(inv_conv, how='left', on=['PROD_COMM','REG_imp'])
            exog_inv['dk'] = exog_inv['dk'] * exog_inv['input_coeff']
            # ? this leads to
            # ? REG_imp | PROD_COMM | investment_good | dk | input_coef
            exog_inv = exog_inv.drop(columns=['input_coeff']).astype({"PROD_COMM":'int'})

            self.investment_exog = exog_inv[['REG_imp','PROD_COMM','TRAD_COMM','dk']].copy()

            # ? disaggregate across export partners (incl. domestic)
            fcf_share = self.fcf_share.astype({'TRAD_COMM':'str'})[['REG_exp','TRAD_COMM','REG_imp','FCF_share']]
            exog_inv = exog_inv.astype({'TRAD_COMM':'str'})
            exog_inv = exog_inv.merge(fcf_share, how='inner', on=['TRAD_COMM','REG_imp'])
            # ? REG_imp | REG_exp | PROD_COMM | investment_good | dk | FCF_share
            exog_inv['dy'] = exog_inv['dk'] * exog_inv['FCF_share']
            exog_inv = exog_inv.drop(columns=['FCF_share','dk']).fillna(0)

            exog_inv = exog_inv.groupby(['REG_imp','REG_exp','TRAD_COMM']).agg({'dy':'sum'}).reset_index()

            self.dy_inv_exog = exog_inv
        
        else:
            self.dy_inv_exog = pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','dy'])
