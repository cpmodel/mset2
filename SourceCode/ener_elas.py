# -*- coding: utf-8 -*-
"""
Created on Mon Jun  5 14:50:43 2023

@author: wb582890
"""

import numpy as np
import pandas as pd
import time
from SourceCode.utils import resolve_comma

class ener_elas:
    """
    INITIALIZED VARIABLES (EXOGENOUS):
      - Elasticities
        - Own-Price Elasticities (ELAS_OP) "OwnPrices.xlsx"
        - Cross-Price Elasticities (ELAS_CP)
            Merge elasticities data from country specific (".._ByCountry.xlsx"),
            rest of Europe (".._ROE.xlsx"), rest of Asia (".._ROA.xlsx"),
            and rest of world (".._ROW.xlsx").
        
    INPUTS FROM OTHER MODULES:
      - exog_vars Module
        - Call IND_BASE (previously IND_sparse) from exog_vars module
          
      - scenario Module
        - Call tax_rate (previously tax_data) from scenario module

    OUTPUTS:
      - ind_ener (previously a_bp_new in IND_sparse)

    """
    def __init__(self, exog_vars, en_cp_elas_list = [
            "EN_CP_ELAS_COU", "EN_CP_ELAS_ROA", "EN_CP_ELAS_ROE", "EN_CP_ELAS_ROW"]):
        
        self.A_id = exog_vars.A_id
        
        self.COU_ID = exog_vars.COU_ID
        # self.EN_OP_ELAS = exog_vars.EN_OP_ELAS
        self.REGIONS = exog_vars.R
        self.PRODUCTS = exog_vars.P
        self.ENERGY = exog_vars.E
        self.ENERGY_LIST = self.ENERGY['Lfd_Nr'].to_list()
        
        # read concordance for world regions to countries
        # self.EN_CP_ELAS_CONC = exog_vars.EN_CP_ELAS_CONC
        # self.EN_OP_ELAS_CONC = exog_vars.EN_OP_ELAS_CONC

        self.IND_BASE = exog_vars.IND_BASE

        # EN_CP_ELAS = {}
        
        # for key in en_cp_elas_list:
        #      value = getattr(exog_vars, key)
        #      value = value.rename(columns={"Fuel":"TRAD_COMM", "Country":"REG_imp"})
        #      EN_CP_ELAS[key] = value
        
        # self.EN_CP_ELAS = pd.concat(EN_CP_ELAS)

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v
        
    # def build_ener_elas(self):
        
    #     EN_OP_ELAS = self.EN_OP_ELAS.melt(id_vars=["Sector","TRAD_COMM"])
    #     EN_OP_ELAS = EN_OP_ELAS.merge(self.EN_OP_ELAS_CONC.rename(columns={'Code':'variable'}))
    #     EN_OP_ELAS = EN_OP_ELAS.rename(columns={"Original Code":"REG_imp", "value":"OP_elas"})
    #     EN_OP_ELAS = EN_OP_ELAS.set_index(["REG_imp","TRAD_COMM"])
        
    #     self.EN_OP_ELAS = EN_OP_ELAS[['OP_elas']]

    #     EN_CP_ELAS = self.EN_CP_ELAS_CONC.merge(self.EN_CP_ELAS, how='left', left_on=['Code'], right_on=['REG_imp'])
    #     EN_CP_ELAS = EN_CP_ELAS.drop(columns=["Country Name","Code","Filename","REG_imp"])
    #     EN_CP_ELAS = EN_CP_ELAS.rename(columns={"Original Code":"REG_imp"})
    #     EN_CP_ELAS = EN_CP_ELAS.set_index(["REG_imp","TRAD_COMM"])
    #     EN_CP_ELAS = EN_CP_ELAS.drop(columns="Sector")
        
    #     self.EN_CP_ELAS = EN_CP_ELAS
        
    #     # get list of energy sector
    #     self.energy_list = sorted(set(
    #         self.EN_OP_ELAS.index.get_level_values("TRAD_COMM")))
    
    def assign_price_change(self):

        ener_elas = self.IND_BASE.reset_index()
        ener_elas = ener_elas.merge(self.common['delta_price_yoy'].rename(columns={'REG_imp':'REG_exp','PROD_COMM':'TRAD_COMM'}), how='left')
        
        ener_elas['dp'] = ener_elas['dp'].fillna(0)
        # flow specific tax (delta_tax) and producer specific price change (dp)
        ener_elas['delta_p'] = ener_elas['dp']

        # * WE NEED TO CALCULATE A WEIGHTED TAX BASED ON THE COMPOSITION OF THE ENERGY SOURCE
        ener_elas['weight'] = ener_elas['z_bp'] / ener_elas.groupby(['REG_imp','PROD_COMM','TRAD_COMM'])['z_bp'].transform('sum')
        ener_elas['weighted_p'] = ener_elas['delta_p'] * ener_elas['weight']
        ener_elas['delta_p'] = ener_elas['weighted_p']
        ener_elas = ener_elas.groupby(['REG_imp','PROD_COMM','TRAD_COMM']).agg({'delta_p':'sum','a_bp':'sum'})

        delta_p = ener_elas["delta_p"]
        delta_p = delta_p[~delta_p.index.duplicated(keep='first')]

        self.delta_p = delta_p

        # drop exporter / origin country

        ener_elas = ener_elas.reset_index().groupby(["REG_imp","PROD_COMM","TRAD_COMM"])["a_bp"].sum()
        ener_elas = ener_elas.to_frame()
        ener_elas = ener_elas.rename(columns={"a_bp": "a_tech"})
        ener_elas = ener_elas.merge(self.delta_p, how='left',on=["REG_imp", "PROD_COMM", "TRAD_COMM"])
        ener_elas = ener_elas.reset_index(level="PROD_COMM", drop=False)
        # ener_elas = ener_elas.join(self.EN_OP_ELAS, how='left')
        # ener_elas = ener_elas.drop(columns="Sector")

        # ener_elas = ener_elas.join(self.EN_CP_ELAS, how="left")

        self.ener_elas = ener_elas

        # in ener_elas, it contains delta tax, 
    
    def MRIO_vec_to_df(self, vector, name, iso3=False):
        # vector is 19680, 120x164
        vec = pd.DataFrame(vector).reset_index()
        vec.columns = ['index', name]
        vec['target-country'] = (np.floor(vec['index'] / len(self.PRODUCTS))).astype('int16') + 1
        vec['target-sector'] =  (vec['index'] % len(self.PRODUCTS)).astype('int16') + 1
        vec[name] = vec[name].astype('float32')
        vec = vec.drop(columns=['index'])
        return vec
    
    def attach_iso3(self, df, regions):
        """ 
        Attaches ISO3 codes from the `regions` input to the dataframe
        `origin-country` and `target-country` have to be present in the dataframe
        """
        regions = regions.drop(columns=['Region_names'])
        regions['Region_acronyms'] = regions['Region_acronyms'].astype('category')
        df = df.merge(regions, how='left', left_on=['target-country'], right_on=['Lfd_Nr']).rename(columns={'Region_acronyms':'target-country-iso3'})\
            .drop(columns=['Lfd_Nr'])
        return df

        
    def calc_tech_coef_ener(self):
        # --- This function calculates technical coefficient based on
        # the energy elasticities and the tax templates
        tech_coef_ener = self.ener_elas.copy()
        tech_coef_ener["delta_tech_coef_OP"] = (
            1 + tech_coef_ener["delta_p"]) ** -(tech_coef_ener["OP_elas"])        
        
        delta_tech_coef_CP = {}

        for col in self.ENERGY_LIST:
            #  self.ener_elas.columns here is:
            # ['PROD_COMM', 'a_tech', 'delta_tax', 'OP_elas', 24, 25, 26, 27, 62, 63, 93, 94]
            # fuel_sec (as defined above are all fuel sectors)
             if col in self.ener_elas.columns:
                 tech_coef_ener["delta_tech_coef_CP_" + str(col)] = (
                     1 + tech_coef_ener["delta_p"]) ** (tech_coef_ener[col])
                 
                #  tech_coef_ener here is the cross-price elasticity [columns] for the product in the row
                 tech_coef_ener = tech_coef_ener.drop(columns=col)

                 delta_tech_coef_CP[col] = tech_coef_ener.groupby(
                     ["REG_imp","PROD_COMM"])["delta_tech_coef_CP_" + str(col)].mean()
                 delta_tech_coef_CP[col] = delta_tech_coef_CP[col].to_frame()
                 delta_tech_coef_CP[col] = delta_tech_coef_CP[col].rename(
                     columns={"delta_tech_coef_CP_" + str(col) : "delta_tech_coef_CP"})
                 delta_tech_coef_CP[col]["TRAD_COMM"] = col
                 delta_tech_coef_CP[col] = delta_tech_coef_CP[col].reset_index()

        # Calculate delta_a_tech based on cross elasticies and own price elasticities
        delta_tech_coef_CP = pd.concat(delta_tech_coef_CP.values())
        delta_tech_coef_CP = delta_tech_coef_CP.set_index(["REG_imp","PROD_COMM","TRAD_COMM"])
        delta_tech_coef_CP = delta_tech_coef_CP.fillna(1)

        tech_coef_ener = tech_coef_ener.reset_index()
        tech_coef_ener = tech_coef_ener.set_index(["REG_imp","PROD_COMM","TRAD_COMM"])
        tech_coef_ener = tech_coef_ener.join(delta_tech_coef_CP)
        tech_coef_ener["delta_tech_coef"] = (
            tech_coef_ener["delta_tech_coef_OP"] * tech_coef_ener["delta_tech_coef_CP"])
        tech_coef_ener["tech_coef_ener"] = (tech_coef_ener["a_tech"] * tech_coef_ener["delta_tech_coef"])
        tech_coef_ener = tech_coef_ener.loc[:,["delta_p","tech_coef_ener"]]
        
        self.tech_coef_ener = tech_coef_ener
        
        return self.tech_coef_ener
        
    def assign_IO_coef_cou(self, tech_coef_ener):
        ind_ener_cou = self.IND_BASE
        ind_ener_cou = ind_ener_cou.join(tech_coef_ener, how='inner')

        # compute new coefficients and corresponding tax revenue by energy carrier
        # assuming constant trade shares, as well as total tax revenue by country and sector
        # (REG_imp and PROD_COMM)

        ind_ener_cou["tech_coef_ener"] = ind_ener_cou["tech_coef_ener"].fillna(
            ind_ener_cou["a_tech"])
        ind_ener_cou["IO_coef_ener"] = (ind_ener_cou["tech_coef_ener"] * 
                                        ind_ener_cou["a_bp"] / ind_ener_cou["a_tech"])
        ind_ener_cou["IO_coef_ener"] = ind_ener_cou["IO_coef_ener"].fillna(0)
        ind_ener_cou["z_bp_ener"] = ind_ener_cou["IO_coef_ener"] * ind_ener_cou["output"]
        
        ind_ener_cou = ind_ener_cou.reset_index(drop=False)
        ind_ener_cou = ind_ener_cou.set_index(["REG_imp","PROD_COMM","REG_exp","TRAD_COMM"])
        
        self.ind_ener_cou_base = ind_ener_cou.loc[:,["a_bp","a_tech","z_bp"]]
        self.ind_ener_cou = ind_ener_cou.loc[:,["IO_coef_ener","tech_coef_ener","z_bp_ener"]]
        
        return self.ind_ener_cou
    
    def build_tax_helper_matrix(self, ind_ener_cou):
        Reg_Sec = ind_ener_cou.reset_index()[
            ["REG_imp","PROD_COMM","REG_exp","TRAD_COMM"]]

        tax_index = sorted(set([(a,b) for a,b in zip(
            Reg_Sec["REG_imp"], Reg_Sec["PROD_COMM"])]))
        
        self.tax_index = tax_index

        ind_ener_cou = pd.concat([self.ind_ener_cou_base, ind_ener_cou], axis=1)
        
        # Build tax Matrix
        tax_matrix = ind_ener_cou.loc[:,["a_bp", "IO_coef_ener"]]
        tax_matrix["delta_IO_coef"] = tax_matrix["IO_coef_ener"] - tax_matrix["a_bp"]
        tax_matrix = tax_matrix.drop(columns=["a_bp", "IO_coef_ener"])
        tax_matrix = tax_matrix.reset_index()
        tax_matrix["IMP_SEC"] = pd.Series(list(zip(tax_matrix["REG_imp"], tax_matrix["PROD_COMM"])))
        tax_matrix["EXP_SEC"] = pd.Series(list(zip(tax_matrix["REG_exp"], tax_matrix["TRAD_COMM"])))
        tax_matrix = tax_matrix.drop(columns=["REG_imp","PROD_COMM","REG_exp","TRAD_COMM"])

        tax_matrix = tax_matrix.set_index(["IMP_SEC","EXP_SEC"])
        tax_matrix = tax_matrix.unstack(level="IMP_SEC")
        tax_matrix.columns = tax_matrix.columns.droplevel(0)

        tax_temp = pd.DataFrame(np.zeros((len(self.A_id),len(tax_index))),
                                index=self.A_id,columns=tax_index)
        tax_temp.loc[tax_matrix.index, tax_matrix.columns] = tax_matrix

        tax_matrix = tax_temp.copy()
        tax_matrix = tax_matrix.fillna(0)
        tax_matrix = tax_matrix.to_numpy()

        # Build Vt Matrix
        sec_temp = pd.DataFrame(np.zeros((len(tax_index), len(self.A_id))),
                                index=tax_index,columns=self.A_id)
        for i in list(sec_temp.index):
            sec_temp[i].loc[[i]] = 1

        sec_matrix = sec_temp.copy()
        sec_matrix = sec_matrix.fillna(0)
        sec_matrix = sec_matrix.to_numpy()

        self.tax_matrix = tax_matrix
        self.sec_matrix = sec_matrix
        
        return self.tax_index, self.tax_matrix, self.sec_matrix
        
    def assign_IO_coef_glo(self, ind_ener_cou):        
        # ind_ener_cou = self.ind_ener_cou
        
        ind_ener_glo = self.IND_BASE.copy()

        for i in list(ind_ener_cou.columns):
            ind_ener_glo[i] = np.nan

        ind_ener_glo.loc[ind_ener_cou.index, ind_ener_cou.columns] = ind_ener_cou

        ind_ener_glo["IO_coef_ener"] = ind_ener_glo["IO_coef_ener"].fillna(
            ind_ener_glo["a_bp"])
        ind_ener_glo["tech_coef_ener"] = ind_ener_glo["tech_coef_ener"].fillna(
            ind_ener_glo["a_tech"])
        ind_ener_glo["z_bp_ener"] = ind_ener_glo["z_bp_ener"].fillna(
            ind_ener_glo["z_bp"])
        
        self.ind_ener_glo = ind_ener_glo.loc[:,[
            "IO_coef_ener", "tech_coef_ener", "z_bp_ener"]]
        
        return self.ind_ener_glo
