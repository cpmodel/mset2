# -*- coding: utf-8 -*-
"""
Created on Thu Jun 29 16:53:55 2023

@author: wb619071
"""

import numpy as np
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df, MRIO_mat_to_df

class normal_output_mod:
    def __init__(self, EXOG_VARS):
        self.LABOR_BASE = EXOG_VARS.LABOR_BASE
        self.VA_BASE = EXOG_VARS.VA_BASE
        self.output = EXOG_VARS.output
        self.R = EXOG_VARS.R
        self.P = EXOG_VARS.P
        self.R_list = EXOG_VARS.R_list
        self.P_list = EXOG_VARS.P_list
        
        # set up params
        load_param = lambda var_: MRIO_df_to_vec(EXOG_VARS.PARAMETERS,'REG_imp','PROD_COMM', var_ ,EXOG_VARS.R_list,EXOG_VARS.P_list)

        self.params = {}
        # self.params['K_ln'] = load_param('normaloutput_K_ln')
        # self.params['K_ln_L1'] = load_param('normaloutput_K_ln_L1')
        # self.params['Q_ln_overline'] = load_param('normaloutput_Q_ln_overline')

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v

    def calc_normal_output_dynamic(self):
        normal_output_growth = self.common['normal_output_growth_helper']
        normal_output_growth = np.nan_to_num(normal_output_growth)

        # simple average (1/4) of last three years CONSTANT price output
        comp1 = (self.common['q1'] + self.common['q2'] + self.common['q3'])/3
        
        # long-term growth (1/4) applied to last year's value
        comp2 = (np.nan_to_num(self.common['q1']/self.common['q2'], posinf=0, neginf=0) \
                 + np.nan_to_num(self.common['q2']/self.common['q3'], posinf=0, neginf=0)) / 2
        comp2 = normal_output_growth * comp2
        normal_output_growth = comp2

        # capital productivity based (1/2)
        comp3 = np.column_stack(
            [np.nan_to_num(self.common['q1']/self.common['k1'], posinf=0, neginf=0), 
             np.nan_to_num(self.common['q2']/self.common['k2'], posinf=0, neginf=0),
             np.nan_to_num(self.common['q3']/self.common['k3'], posinf=0, neginf=0)])
        comp3 = np.amax(comp3, axis=1)
        comp3 = comp3 * self.common['k']

        normal_output = comp1 * 1/4 + comp2 * 1/4 + comp3 * 1/2
        # cap on zero
        normal_output[normal_output<0] = 0.0
        
        return({"normal_output" : normal_output, "normal_output_helper": normal_output_growth})        