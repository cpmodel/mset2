# -*- coding: utf-8 -*-
"""
Created on Thu Jun 29 17:06:40 2023

@author: wb582890
"""

import numpy as np
import pandas as pd
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df, MRIO_mat_to_df
import copy

class price:
    """
    This class collects the variables and parameters related to prices and calculates 
    prices based on exogenous costs.

    Parameters
    ----------
    EXOG_VARS : class
        Class for exogenous variables.
    IO_model : class
        Class for Input-Ouput model.
    BTA_cou : class
        Class for Border Trade Adjustment (BTA).
    
    Methods
    -----------
    build_prod_cost_base_vector
        Calculates base production costs from exogenous production costs.
    calc_positive_and_negative_L
        Calculates parameters for positive and negative price changes.
    second_order_dprice
        Calculates second order price impacts.
    build_prod_cost_vector
        Calculates production costs from exogenous production costs.
    calc_dp_pre_trade_bta
        Calculates price changes before trade.

    Inputs:
    - exog_prod_cost: DataFrame containing exogenous production cost data
    - GLORIA_rp: DataFrame containing GLORIA region and sector identifiers
    - L_base: Base Leontief inverse matrix
    
    Output:
    - delta_p_pm: DataFrame containing calculated price changes
    - delta_p_bta_exim: Dataframe containing domestic price change with no bta

    """
    def __init__(self, EXOG_VARS, IO_model, BTA_cou):
        self.COU_ID = EXOG_VARS.COU_ID
        self.mrio_id = EXOG_VARS.mrio_id
        self.A_id = EXOG_VARS.A_id
        
        self.A_BASE = IO_model.A_BASE
        self.IO_model = IO_model

        self.R_list = EXOG_VARS.R['Region_acronyms'].tolist()
        self.P_list = EXOG_VARS.P['Lfd_Nr'].to_list()
        self.R = EXOG_VARS.R
        self.P = EXOG_VARS.P

        self.DIMS = len(self.R_list) * len(self.P_list)

        self.bta = BTA_cou.bta
        
        if self.bta == 1:
            self.bta_exp = BTA_cou.bta_exp
        elif self.bta == -1 or self.bta == 0:
            self.bta_imp = BTA_cou.bta_imp

        # set up params
        load_param = lambda var_: MRIO_df_to_vec(EXOG_VARS.PARAMETERS,'REG_imp','PROD_COMM', var_ ,EXOG_VARS.R_list,EXOG_VARS.P_list)

        self.params = {}
        self.params['dneg_C'] = load_param('price_dneg_C')
        self.params['dpos_C'] = load_param('price_dpos_C')
        self.params['dev_normaloutput_L1'] = load_param('price_dev_normaloutput_L1')
        self.params['dev_meanprofit_L1'] = load_param('price_dev_meanprofit_L1')
        self.params['output_growth_L1'] = load_param('price_output_growth_L1')

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v
        
    def build_prod_cost_base_vector(self, exog_prod_cost_base):
        """
        
        Parameters
        ----------
        exog_prod_cost_base : TYPE
            DESCRIPTION.

        Returns
        -------
        TYPE
            DESCRIPTION.

        """
        v_base = exog_prod_cost_base.copy()
        v_base["IMP_SEC"] = list(zip(v_base["REG_imp"], v_base["PROD_COMM"]))
        v_base = v_base.drop(columns=["REG_imp","PROD_COMM"])
        v_base = v_base.set_index(["IMP_SEC"])

        v_temp = pd.DataFrame(np.zeros(self.DIMS), index=self.A_id,
                              columns=["delta_prod_cost_rel_base"])
        v_temp.loc[self.A_id] = v_base
        v_base = v_temp.fillna(1)

        v_base = v_base["delta_prod_cost_rel_base"].to_numpy()
        
        self.v_base = v_base
        
        return self.v_base
    
    def dp_normal_output(self, dev_normal_output_L1):
        return(dev_normal_output_L1 * self.params['dev_normaloutput_L1'])
    
    def dp_profit_rate(self, dev_profit_rate_L1):
        return(dev_profit_rate_L1 * self.params['dev_meanprofit_L1'])
    
    def dp_output_growth(self, output_g_L1):
        return(output_g_L1 * self.params['output_growth_L1'])
    
    def update_A_BASE(self, A_trade):
        self.A_BASE = A_trade
    
    def calc_positive_and_negative_L(self):
        # A_BASE is matrix, rows: producers; columns: users
        positive_A_BASE = self.A_BASE * self.params['dpos_C']
        # no self-indirect effect!
        np.fill_diagonal(positive_A_BASE, 0)
        L_positive = self.IO_model.invert_A_base(A_BASE_ext=positive_A_BASE)
        np.fill_diagonal(L_positive, 0)
        self.L_positive = L_positive

        # B_BASE is matrix, rows: producers; columns: users
        negative_A_BASE = self.A_BASE * self.params['dneg_C']
        np.fill_diagonal(negative_A_BASE, 0)
        L_negative = self.IO_model.invert_A_base(A_BASE_ext=negative_A_BASE)
        np.fill_diagonal(L_negative, 0)
        self.L_negative = L_negative

    def second_order_dprice(self, v_impact, direct_impact="direct", year=None):
        # v_impact is the price impact vector (1st order); v_impact values are 0.1 for +10%
        # we apply Dneg and Dpost coefficients, these are negative and positive unit cost change respectively
        # ! this is IMPORTANT: we WANT TO KEEP THE DIRECT IMPACT INTACT, regardless of the parameters
        # ? ok, so originally this has been working with a Ghoshian price impact, however a Ghoshian price impact also means
        # ? that given an impact of 1% in sector 'A' through linkages and multiple loops the impact in sector 'B' can easily be 
        # ? higher than 1% (e.g., 4%) now this is something we do not want, because it increases prices and lot and assumes
        # ? that there are infinite periods of price adjustment

        # ? so we try out an alternative solution, which is to simply use 
        
        v_positive = copy.deepcopy(v_impact)
        v_positive[v_positive<0] = 0

        v_negative = copy.deepcopy(v_impact)
        v_negative[v_negative>0] = 0

        if direct_impact == "direct":
            pass
        elif direct_impact == "passthrough":
            v_positive = v_positive * self.params['dpos_C'] 
            v_negative = v_negative * self.params['dneg_C']
        else:
            raise KeyError("second_order_dprice takes either 'direct' or 'passthrough' as argument")

        dp_positive = np.dot(self.L_positive.T, v_positive)        
        dp_negative = np.dot(self.L_negative.T, v_negative)
        
        dp_full = dp_positive + dp_negative + v_positive + v_negative
        

        return({
            'dp_full': dp_full,
            'dp_positive': dp_positive, 
            'dp_negative': dp_negative,
            'v_calculated': v_positive + v_negative
        })
    
    def build_prod_cost_vector(self, exog_prod_cost):
        v_ener = exog_prod_cost.copy()
        v_ener['prod_cost_rel'] = pd.to_numeric(v_ener['prod_cost_rel'])
        mIndex_in = pd.MultiIndex.from_frame(v_ener[['REG_imp','PROD_COMM']])
        v_ener = v_ener.drop(columns=["REG_imp","PROD_COMM"])
        v_ener = v_ener.set_index(mIndex_in)

        mIndex = pd.MultiIndex.from_tuples(self.A_id)
        v_temp = pd.DataFrame(np.empty(self.DIMS), index=mIndex,
                              columns=["delta_prod_cost_rel"])
        v_temp[:] = np.nan
        v_temp.loc[v_ener.index] = v_ener
        v_ener = v_temp.fillna(1)

        v_ener = v_ener["delta_prod_cost_rel"].to_numpy()
        
        self.v_ener = v_ener
        
        return self.v_ener
    
    def calc_dp_pre_trade_bta(self, dp_pre_trade, cbam_incidence, mrio, price_index):

        # in a REG_imp - PROD_COMM
        mrio = mrio.reset_index()
        dp_pre_trade_ = dp_pre_trade.copy()
        dp_pre_trade_['delta_p'] = dp_pre_trade_['delta_p'].fillna(0)
        mrio = mrio.merge(dp_pre_trade_, how='left', on=['REG_exp','TRAD_COMM'])
        # adds delta_p
        mrio = mrio.merge(cbam_incidence.astype({'TRAD_COMM':'int','PROD_COMM':'int'}), how='left', on=['REG_imp','REG_exp','TRAD_COMM','PROD_COMM']).fillna(0)
        mrio = mrio.merge(price_index.rename(columns={'REG_imp':'REG_exp','PROD_COMM':'TRAD_COMM'}), how='left', on=['REG_exp','TRAD_COMM'])
        mrio['delta_cbam'] = np.nan_to_num(mrio['cbam_cost'] / (mrio['z_bp_ener'] * mrio['price_index']), nan=0.0, posinf=0.0, neginf=0.0)

        # in theory this DOES NOT CHANGE anything
        mrio = mrio.groupby(['REG_imp','REG_exp','TRAD_COMM']).agg({'delta_p':'mean','delta_cbam':'mean'}).reset_index()
        mrio['delta_p'] = mrio['delta_p'] + mrio['delta_cbam']

        dp_pre_trade = mrio[['REG_imp','REG_exp','TRAD_COMM','delta_p']]            
        self.dp_pre_trade = dp_pre_trade

        return self.dp_pre_trade