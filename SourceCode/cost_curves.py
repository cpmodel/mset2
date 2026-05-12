"""

cost_curves

"""

import numpy as np
import pandas as pd
from copy import deepcopy

class cost_curves:

    def __init__(self, exog_vars):

        #? REG_imp	PROD_COMM	a	b	c	d	e	f
        #? AFR	24	-12.4366864	0.952504921	-0.021782877	0.000164866	27.73867995	2.049988733

        self.cost_curves_table = exog_vars.COST_CURVES
        
        self.P = exog_vars.P
        self.R = exog_vars.R
        self.R_list = exog_vars.R['Region_acronyms'].tolist()
        self.P_list = exog_vars.P['Lfd_Nr'].to_list()

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v

    def calc_cost_impact(self, dq=None):

        if not (dq is None):
            q_curr = deepcopy(self.common['q_current'])
            q_curr['output'] = q_curr['output'] + dq
        else:
            q_curr = self.common['q_current']

        # q, q_prev, q_base all dfs such as REG_imp | PROD_COMM | output
        q_base = self.common['q_base'].rename(columns={'output':'q_base'})
        q_prev = self.common['q_prev'].rename(columns={'output':'q_prev'})
        
        df = pd.concat([q_base, q_prev[['q_prev']], q_curr[['output']]], axis=1)
        df['x_prev'] = df['q_prev'] / df['q_base']
        df['x_curr'] = df['output'] / df['q_base']
        df = df.merge(self.cost_curves_table, how='left', on=['REG_imp','PROD_COMM']).fillna(0)

        df['p_prev'] = df['a'] + df['b'] * (df['x_prev']**df['f']+df['e']) + df['c'] * (df['x_prev']**df['f']+df['e'])**2 + df['d'] * (df['x_prev']**df['f']+df['e'])**3
        df['p_curr'] = df['a'] + df['b'] * (df['x_curr']**df['f']+df['e']) + df['c'] * (df['x_curr']**df['f']+df['e'])**2 + df['d'] * (df['x_curr']**df['f']+df['e'])**3

        p_min = 0.01
        df['p_prev'] = df['p_prev'].clip(lower=p_min)
        df['p_curr'] = df['p_curr'].clip(lower=p_min)

        df['cost_change_share'] = 0.0
        # positive
        df['cost_change_share_pos'] = np.nan_to_num((df['x_curr']-df['x_prev'])/df['x_curr'], nan=0.0, posinf=0.0, neginf=0.0)
        df.loc[df['x_prev'] <= df['x_curr'], 'cost_change_share'] = df.loc[df['x_prev'] <= df['x_curr'], 'cost_change_share_pos']
        # negative
        df['cost_change_share_neg'] = np.nan_to_num((df['x_prev']-df['x_curr'])/df['x_prev'], nan=0.0, posinf=0.0, neginf=0.0)
        df.loc[df['x_prev'] >= df['x_curr'], 'cost_change_share'] = df.loc[df['x_prev'] >= df['x_curr'], 'cost_change_share_neg']

        df['input_cost_change'] = np.nan_to_num(df['p_curr']/df['p_prev'], nan=1.0, posinf=1.0, neginf=1.0) - 1.0

        #? then use input_cost_change to
        
        # TODO -> increase labour demand
        # TODO -> increase capital demand
        # TODO -> increase inputs

        return df[['REG_imp','PROD_COMM','cost_change_share','input_cost_change']] 
    
    def build_io_change(self, io_impacts):

        # ? ok so the issue with IO changes is that it should not apply to the whole IO (bc cost doesn't go up in existing part)
        # ? only in the changed part, so that means that 
        # ? [input_cost_change]*([volume_change]/[total]), whichis is [input_cost_change] * [cost_change_share]

        df = self.common['empty_io']

        io_impacts_ = deepcopy(io_impacts)
        io_impacts_['input_cost_change_adj'] = io_impacts_['input_cost_change'] * io_impacts_['cost_change_share']
        io_impacts_ = io_impacts_.drop(columns=['input_cost_change','cost_change_share'])

        df = df.merge(io_impacts_, how='left', on=['REG_imp','PROD_COMM']).fillna(0)

        df = df.rename(columns={'input_cost_change_adj':'Value'})
        df['Type'] = 'rel'

        df = df.query("Value != 0")

        return df