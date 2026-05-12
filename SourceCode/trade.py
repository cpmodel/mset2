# -*- coding: utf-8 -*-
"""
Created on Thu Jun 29 17:11:57 2023

@author: wb582890
"""

import pandas as pd
import numpy as np
import time
from SourceCode.utils import MRIO_vec_to_df, MRIO_df_to_vec

class trade:
    """
    This class collects the variables and parameters related to trade and calculates 
    GDP and price dynamics, and applies elasticities to FD and trade IO coefficients.

    Parameters
    ----------
    EXOG_VARS : class
        Class for exogenous variables.
    
    Methods
    -----------
    calculate_dynamics
        Calculates GDP and price dynamics.
    calc_FD_substitution
        Calculates FD substitution based on elasticities.
    calc_IO_coef
        Re-calculates IO coefficients based on trade elasticities.
    """
    
    def __init__(self, EXOG_VARS):
        # set up frame
        self.frame_ = pd.DataFrame({"PROD_COMM":EXOG_VARS.P_list,"key":1}).merge(pd.DataFrame({"REG_imp":EXOG_VARS.R_list, "key":1})).drop(columns=['key'])
        self.R_list = EXOG_VARS.R_list
        self.P_list = EXOG_VARS.P_list
        
        # set up params
        param_cols = ['REG_imp','PROD_COMM'] + [c for c in EXOG_VARS.PARAMETERS.columns if ('trade_' in c)]
        self.params = EXOG_VARS.PARAMETERS[param_cols].copy()
        self.params = self.params.rename(columns={'PROD_COMM':'TRAD_COMM'})
        self.params.columns = [x.replace("trade_","") for x in self.params.columns]

        # bring in final demand components
        self.FCF_BASE = EXOG_VARS.FCF_BASE
        self.HH_BASE = EXOG_VARS.HH_BASE
        self.GOV_BASE = EXOG_VARS.GOV_BASE

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v

    def calculate_dynamics(self):
        # calculate dynamics
        # ! this is nominal GDP!
        # TODO need to be deflated
        GDP_prev1 = self.common['va_prev1'].groupby('REG_imp').sum()[['compensation','taxes','profit']].sum(axis=1).reset_index()
        GDP_prev2 = self.common['va_prev2'].groupby('REG_imp').sum()[['compensation','taxes','profit']].sum(axis=1).reset_index()
        GDP_prev3 = self.common['va_prev3'].groupby('REG_imp').sum()[['compensation','taxes','profit']].sum(axis=1).reset_index()
        dynamics_gdp = GDP_prev1.rename(columns={0:"GDP_prev1"}).merge(GDP_prev2.rename(columns={0:'GDP_prev2'}))\
            .merge(GDP_prev3.rename(columns={0:'GDP_prev3'}))
        
        dynamics_price = self.common['price_index'].rename(columns={'PROD_COMM':'TRAD_COMM','REG_imp':'REG_exp'})
        dynamics_price = dynamics_price.merge(self.common['price_index_prev'].rename(columns={'PROD_COMM':"TRAD_COMM",'price_index':'price_index_prev','REG_imp':'REG_exp'}))
        dynamics_price['price_index'] = dynamics_price['price_index'].fillna(1)
        dynamics_price['price_index_prev'] = dynamics_price['price_index_prev'].fillna(1)

        self.dynamics_gdp = dynamics_gdp
        self.dynamics_price = dynamics_price

    def calc_FD_substitution(self, dp_pre_trade):

        on_ = ['REG_imp','REG_exp','TRAD_COMM']
        FD = self.FCF_BASE.reset_index().merge(self.HH_BASE.reset_index(), how='outer', on=on_).merge(self.GOV_BASE.reset_index(), how='outer', on=on_)
        FD = FD.fillna(0)
        FD['total'] = FD['VDFA'] + FD['VIPA'] + FD['VIGA']

        # add and apply elasticity
        FD = FD.merge(self.params, on=['REG_imp','TRAD_COMM'])
        FD = FD.merge(self.dynamics_price, how='left', on=['TRAD_COMM','REG_exp'])
        FD = FD.merge(self.dynamics_gdp, how='left', on=['REG_imp'])
        FD = FD.merge(dp_pre_trade, how='left', on=["TRAD_COMM","REG_imp","REG_exp"])
        
        # fill
        FD['delta_p'].fillna(0, inplace=True)
        FD['price_index'].fillna(1, inplace=True)
        FD['price_index_prev'].fillna(1, inplace=True)

        # make nominal
        FD['total_constant'] = FD['total']
        FD['total'] = FD['total'] * FD['price_index'] * (1 + FD['delta_p'])

        # apply elasticity; step by step just for the code to be clear
        FD['new_total'] = FD['total']
        FD['new_total'] = FD['new_total'] + FD['total'] * (FD['delta_p'] * FD['p_ln_L1'])
        FD['new_total'] = FD['new_total'] + FD['total'] * ((FD['price_index'] / FD['price_index_prev']- 1) * FD['p_ln_L2'])
        FD['new_total'] = FD['new_total'] + FD['total'] * ((FD['GDP_prev1']/FD['GDP_prev2'] - 1) * FD['GDP_ln_L1'])


        # ! so the trade cap is the following: a connection (flow) cannot go below 5% of its initial value if trade flow and 25% of its initial value if domestic
        sel = (FD['new_total'] < FD['total'] * 0.50) & (FD['REG_imp'] != FD['REG_exp'])
        FD.loc[sel, 'new_total'] = FD.loc[sel, 'total'] * 0.50 

        sel = (FD['new_total'] < FD['total'] * 0.75) & (FD['REG_imp'] == FD['REG_exp'])
        FD.loc[sel, 'new_total'] = FD.loc[sel, 'total'] * 0.75 
        
        # this does not apply, because no connection goes negative:
        #  IF A CONNECTION IS LOST IT STAYS LOST...
        #FD.loc[FD['new_total'] <= 0, 'new_total'] = 0 

        # make constant
        FD['total'] = FD['total_constant']
        FD['new_total'] = FD['new_total'] / (FD['price_index'] * (1 + FD['delta_p']))

        # but we need to maintain the technology receipes
        FD['category_spend'] = FD.groupby(['REG_imp','TRAD_COMM'])['total'].transform('sum')
        FD['trade_share'] = FD['new_total'] / FD.groupby(['REG_imp','TRAD_COMM'])['new_total'].transform('sum')
        FD['new_total'] = FD['category_spend'] * FD['trade_share']

        # we need to recreate the three FD vectors (just change!)
        FD['delta'] = FD['new_total'] - FD['total']

        FD = FD[['REG_imp','REG_exp','TRAD_COMM','VDFA','VIPA','VIGA','delta','total','price_index','delta_p']].copy()
        FD['dVDFA'] = (FD['VDFA'] / FD['total']) * FD['delta']
        FD['dVIGA'] = (FD['VIGA'] / FD['total']) * FD['delta']
        FD['dVIPA'] = (FD['VIPA'] / FD['total']) * FD['delta']

        # compiled DY
        dy_trade_hh = MRIO_df_to_vec(FD, "REG_exp", "TRAD_COMM", 'dVIPA', self.R_list, self.P_list)
        dy_trade_fcf = MRIO_df_to_vec(FD, "REG_exp", "TRAD_COMM", 'dVDFA', self.R_list, self.P_list)
        dy_trade_gov = MRIO_df_to_vec(FD, "REG_exp", "TRAD_COMM", 'dVIGA', self.R_list, self.P_list)

        return({'dy':{
            'dy_trade_hh': dy_trade_hh,
            'dy_trade_fcf': dy_trade_fcf,
            'dy_trade_gov': dy_trade_gov
        }, '3d' : {
            'HH_d': FD[['REG_imp','REG_exp','TRAD_COMM','dVIPA']],
            'FCF_d': FD[['REG_imp','REG_exp','TRAD_COMM','dVDFA']],
            'GOV_d': FD[['REG_imp','REG_exp','TRAD_COMM','dVIGA']]
        }
        })
        
    def calc_IO_coef(self, ind_ener_glo, dp_pre_trade, year):

        # we put the elasticities estimated by Marco on the VALUE of the flows, so let's do
        trade_df = ind_ener_glo.reset_index()[['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','z_bp_ener','IO_coef_ener']].copy()
        # get rid of strange values
        trade_df['output'] = trade_df['z_bp_ener'] / trade_df['IO_coef_ener']
        trade_df.loc[trade_df['z_bp_ener'] < 0, 'z_bp_ener'] = 0
        
        # first add elasticity parameters
        trade_df = trade_df.merge(self.params, on=['REG_imp','TRAD_COMM'])
        # second merge price changes
        trade_df = trade_df.merge(dp_pre_trade, how='left', on=["TRAD_COMM","REG_imp","REG_exp"])
        # third the dynamic variables
        trade_df = trade_df.merge(self.dynamics_price, how='left', on=['TRAD_COMM','REG_exp'])
        trade_df = trade_df.merge(self.dynamics_gdp, how='left', on=['REG_imp'])

        # fill
        trade_df['delta_p'].fillna(0, inplace=True)
        trade_df['price_index'].fillna(1, inplace=True)
        trade_df['price_index_prev'].fillna(1, inplace=True)

        # make nominal
        trade_df['z_bp_ener_constant'] = trade_df['z_bp_ener']
        trade_df['z_bp_ener'] = trade_df['z_bp_ener'] * trade_df['price_index'] * (1 + trade_df['delta_p'])

        # apply elasticity; step by step just for the code to be clear
        trade_df['z_bp_new'] = trade_df['z_bp_ener']
        trade_df['z_bp_new'] = trade_df['z_bp_new'] + trade_df['z_bp_ener'] * (trade_df['delta_p'] * trade_df['p_ln_L1'])
        trade_df['z_bp_new'] = trade_df['z_bp_new'] + trade_df['z_bp_ener'] * ((trade_df['price_index'] / trade_df['price_index_prev'] - 1) * trade_df['p_ln_L2'])
        trade_df['z_bp_new'] = trade_df['z_bp_new'] + trade_df['z_bp_ener'] * ((trade_df['GDP_prev1']/trade_df['GDP_prev2'] - 1) * trade_df['GDP_ln_L1'])

        # ! so the trade cap is the following: a connection (flow) cannot go below 5% of its initial value if trade flow and 25% of its initial value if domestic
        sel = (trade_df['z_bp_new'] < trade_df['z_bp_ener'] * 0.50) & (trade_df['REG_imp'] != trade_df['REG_exp'])
        trade_df.loc[sel, 'z_bp_new'] = trade_df.loc[sel, 'z_bp_ener'] * 0.50 

        sel = (trade_df['z_bp_new'] > trade_df['z_bp_ener'] * 1.50) & (trade_df['REG_imp'] != trade_df['REG_exp'])
        trade_df.loc[sel, 'z_bp_new'] = trade_df.loc[sel, 'z_bp_ener'] * 1.50 

        sel = (trade_df['z_bp_new'] < trade_df['z_bp_ener'] * 0.75) & (trade_df['REG_imp'] == trade_df['REG_exp'])
        trade_df.loc[sel, 'z_bp_new'] = trade_df.loc[sel, 'z_bp_ener'] * 0.75 

        sel = (trade_df['z_bp_new'] > trade_df['z_bp_ener'] * 1.25) & (trade_df['REG_imp'] == trade_df['REG_exp'])
        trade_df.loc[sel, 'z_bp_new'] = trade_df.loc[sel, 'z_bp_ener'] * 1.25 
        
        # this does not apply, because no connection goes negative:
        # IF A CONNECTION IS LOST IT STAYS LOST...
        # trade_df.loc[trade_df['z_bp_new'] <= 0, 'z_bp_new'] = 0

        # make constant
        trade_df['z_bp_new'] = trade_df['z_bp_new'] / (trade_df['price_index'] * (1 + trade_df['delta_p']))
        trade_df['z_bp_ener'] = trade_df['z_bp_ener_constant']

        # but we need to maintain the technology receipes
        trade_df['technology_spend'] = trade_df.groupby(['REG_imp','PROD_COMM','TRAD_COMM'])['z_bp_ener'].transform('sum')
        trade_df['trade_share'] = trade_df['z_bp_new'] / trade_df.groupby(['REG_imp','PROD_COMM','TRAD_COMM'])['z_bp_new'].transform('sum')
        trade_df['z_bp_ener'] = trade_df['technology_spend'] * trade_df['trade_share']
        trade_df['IO_coef_trade'] = trade_df['z_bp_ener'] / trade_df['output']

        trade_df = trade_df[['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','IO_coef_trade']].copy()
        trade_df.set_index(['REG_imp','PROD_COMM','REG_exp','TRAD_COMM'], inplace=True)
       
        return trade_df
