# -*- coding: utf-8 -*-
"""
Created on Thu Jun  8 16:16:13 2023

@author: meime
"""

import pandas as pd

class tax_rev:
    def __init__(self, EXOG_VARS, tax_cou, bta=0):
        self.ENERGY = EXOG_VARS.E
        self.ENERGY_LIST = self.ENERGY['Lfd_Nr'].to_list()

        self.hh_ener = EXOG_VARS.HH_BASE.loc[:, :, self.ENERGY_LIST]

        self.IND_BASE = EXOG_VARS.IND_BASE.reset_index()
        
        self.hh_ener_idx = self.hh_ener.index
        self.bta = bta

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v
    
    def calc_tax_rev_base(self, tax_rate):
        tax_rate = tax_rate.astype({'PROD_COMM':'int64','TRAD_COMM':'int64'})
        tax_rev_base = self.IND_BASE[['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','z_bp']].merge(tax_rate, how='left', on=["REG_imp", "PROD_COMM", "TRAD_COMM","REG_exp"])
        tax_rev_base = tax_rev_base.merge(self.common['price_index'].rename(columns={'PROD_COMM':'TRAD_COMM','REG_imp':'REG_exp'}), how='left')
        tax_rev_base['delta_tax'].fillna(0, inplace=True)
        tax_rev_base["tax_rev_base"] = tax_rev_base["z_bp"] * tax_rev_base["delta_tax"] * tax_rev_base['price_index']

        self.tax_rev_base = tax_rev_base.reset_index().set_index(['REG_imp','PROD_COMM','REG_exp','TRAD_COMM'])
        self.tax_rev_base = self.tax_rev_base[['tax_rev_base']]
        
        return self.tax_rev_base
    
    def calc_tax_rev_prod_base(self, tax_rev_base):
        tax_rev_prod_base = tax_rev_base.groupby(["REG_imp","PROD_COMM"])["tax_rev_base"].sum()
        tax_rev_prod_base = tax_rev_prod_base.to_frame()
        tax_rev_prod_base = tax_rev_prod_base.rename(
            columns={"tax_rev_base": "tax_rev_prod_base"})

        self.tax_rev_prod_base = tax_rev_prod_base

        return self.tax_rev_prod_base
    
    def calc_tax_rev_hh_base(self, tax_rate_hh):

        tax_rate_hh = tax_rate_hh.astype({'TRAD_COMM':'str'})
        hh_ener = self.hh_ener.reset_index().astype({'TRAD_COMM':'str'})

        tax_rev_hh_base = hh_ener.merge(tax_rate_hh[tax_rate_hh['PROD_COMM']=='FD_1'].drop(columns=['PROD_COMM']), how='left', on=["REG_imp", "TRAD_COMM", "REG_exp"])
        tax_rev_hh_base['delta_tax_hh'].fillna(0, inplace=True)
        
        tax_rev_hh_base["tax_rev_hh_base"] = tax_rev_hh_base["VIPA"] * tax_rev_hh_base["delta_tax_hh"]
        
        self.tax_rev_hh_base = tax_rev_hh_base.loc[:,["tax_rev_hh_base"]]
        self.tax_rev_hh_base = self.tax_rev_hh_base.set_index(self.hh_ener_idx)

        return self.tax_rev_hh_base
    
    def subtract_prev(self, recyc_rev, recyc_prev):
        recyc_prev_ = recyc_prev.copy().reset_index()
        recyc_prev_.columns = ["{}_prev".format(x) if x != 'REG_imp' else x for x in recyc_prev_.columns] 
        df = recyc_rev.reset_index().merge(recyc_prev_, how='left', on=['REG_imp']).fillna(0)
        df['recyc_govt_base'] = df['recyc_govt_base'] - df['recyc_govt_base_prev']
        df['recyc_inc_base'] = df['recyc_inc_base'] - df['recyc_inc_base_prev']
        df['recyc_payr_base'] = df['recyc_payr_base'] - df['recyc_payr_base_prev']
        df['recyc_inv_base'] = df['recyc_inv_base'] - df['recyc_inv_base_prev']

        recyc_rev_nat = df[['REG_imp','recyc_govt_base','recyc_inc_base','recyc_payr_base','recyc_inv_base']].copy()
        recyc_rev_nat = recyc_rev_nat.set_index(['REG_imp'])

        return recyc_rev_nat
    
    def calc_recyc_rev(self, tax_rev, rev_split, rev_subtract_exp_base=None):

        rev_split = rev_split[~rev_split['REG_imp'].isna()]
        
        # ? keep in mind this is all nominal!!!
        # ! also keep in mind that the revenue that we keep track should be ONLY change from last year
        # ! hence need to subtract last year's values
        
        # rev_subtract_exp_base = rev_subtract_exp_base.reset_index().groupby(['REG_exp']).agg({'rev_subtract_exp_base':'sum'}).reset_index()
        # rev_subtract_exp_base = rev_subtract_exp_base.rename(columns={'REG_exp':'REG_imp'})

        recyc_rev_nat = tax_rev
        # recyc_rev_nat = tax_rev.merge(rev_subtract_exp_base, how='outer', on=['REG_imp'])
        recyc_rev_nat = recyc_rev_nat.merge(rev_split, how="left", on=["REG_imp"])

        # recyc_rev_nat["net_tax_rev_nat_base"] = (
        #     recyc_rev_nat["tax_rev"].fillna(0) )
            # - recyc_rev_nat["rev_subtract_exp_base"].fillna(0))

        recyc_rev_nat["recyc_govt_base"] = recyc_rev_nat["tax_rev"] * recyc_rev_nat["govt_spend"] # done
        recyc_rev_nat["recyc_inc_base"] = recyc_rev_nat["tax_rev"] * recyc_rev_nat["inc_tax"] # done
        recyc_rev_nat["recyc_payr_base"] = recyc_rev_nat["tax_rev"] * recyc_rev_nat["payr_tax"]
        # ! payroll is NOT working as of 4/16/2025 [BKD]
        recyc_rev_nat["recyc_inv_base"] = recyc_rev_nat["tax_rev"] * recyc_rev_nat["pub_inv"] # done
        
        recyc_rev_nat = recyc_rev_nat.set_index(["REG_imp"])

        self.recyc_rev_nat = recyc_rev_nat.loc[
            :, ["recyc_govt_base", "recyc_inc_base", "recyc_payr_base", "recyc_inv_base"]]
        
        return self.recyc_rev_nat
        
    def calc_tax_iter_cond(self, old, new):
        # Iter_comment:
        # Collect additional labor income
        dtax = old.merge(new.rename(columns={'emission_cost':'emission_cost_prev'}))
        dtax['emission_cost'] = dtax['emission_cost'] / dtax['emission_cost_prev'] - 1.0
        dtax['emission_cost'].fillna(0, inplace=True)
        dtax = dtax.drop(columns=['emission_cost_prev'])  
        return dtax
    
    def build_tax_rev_result(self, tax_rev_prod, tax_rev_hh):
        tax_rev_hh_final = tax_rev_hh.groupby(["REG_imp"])["tax_rev_hh"].sum().to_frame()
        tax_rev_hh_final["PROD_COMM"] = "finalhhdemand"
        tax_rev_hh_final = tax_rev_hh_final.set_index("PROD_COMM", append=True)
        tax_rev_hh_final.columns = ["tax_rev_prod_base"]

        tax_revenue = pd.concat([tax_rev_prod, tax_rev_hh_final])
        tax_revenue = tax_revenue.reset_index(drop=False)
        
        return tax_revenue
