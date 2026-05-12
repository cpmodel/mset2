# -*- coding: utf-8 -*-
"""
Created on Thu Jun 29 15:59:53 2023

@author: wb582890
"""

import numpy as np
import pandas as pd
import scipy.io
import pickle
import os

import time

def normalize_path(path):
    """Convert Windows-style paths to platform-independent paths."""
    return path.replace('\\', os.path.sep)

class exog_vars:

    def __init__(self, IO_PATH = os.getcwd()):
        """_This class collects all the exogenous variables: elasticity parameters,
        Input-Output and Final Demand information to be passed on to the modules,
        loads the parsed GLORIA IO and final demand raw data.

        Parameters
        ----------
        IO_PATH : _str_, optional
            _root folder of MINDSET model_, by default current working directory

        """        
        start_time = time.time()
        
        self.IO_PATH = IO_PATH
        self.GLORIAv = 'v57'
        
        var_path = os.path.join(self.IO_PATH, "Data", "MSET_data", "Variable_list_MINDSET.xlsx")
        var_data = pd.read_excel(var_path, "variables")

        path_dict = {key: value for key, value in zip(
            var_data['Variable name (new)'], var_data['Location'])}
        type_dict = {key: value for key, value in zip(
            var_data['Variable name (new)'], var_data['Type'])}
        
        self.R = pd.read_excel(var_path, 'R')
        self.R = self.R.sort_values(by="Lfd_Nr")
        self.R_list = self.R['Region_acronyms'].to_list()

        self.P = pd.read_excel(var_path, 'P')
        self.P = self.P.sort_values(by="Lfd_Nr")
        self.P_list = self.P['Lfd_Nr'].to_list()

        self.E = pd.read_excel(var_path, 'E')
        self.E = self.E.sort_values(by="Lfd_Nr")

        self.MULTIYEAR = False
        
        
        for key in path_dict.keys():
            if key.isupper():
                path_value, type_value = path_dict[key], type_dict[key]

                # empty value
                if isinstance(path_value, float):
                    if key == 'SCENARIO':
                        pass
                    else:
                        print("WARNING: No input file specified for {}".format(key))
                        pass
                
                elif path_value.endswith('.xlsx'):
                    # Reading Excel files as DataFrame
                    value = pd.read_excel(os.path.join(self.IO_PATH, normalize_path(path_value)))
                    
                elif path_value.endswith('.mat'):
                    # Reading mat files as NumPy Matrix
                    try:
                        value = scipy.io.loadmat(os.path.join(self.IO_PATH, normalize_path(path_value)))
                    except FileNotFoundError:
                        print(f"{key} file is not found, will be parsed in IO module.")
                                        
                elif (path_value.endswith('.pkl') and type_value == "List"):
                    # Reading pickle files as list
                    with open(os.path.join(self.IO_PATH, normalize_path(path_value)), 'rb') as f:
                        value = pickle.load(f)
                    del f
                
                elif (path_value.endswith('.pkl') and type_value == "DataFrame"):
                    # Reading pickle files as DataFrame
                    value = pd.read_pickle(os.path.join(self.IO_PATH, normalize_path(path_value)))
                
                elif path_value.endswith('.csv'):
                    # Reading csv files as DataFrame
                    value = pd.read_csv(os.path.join(self.IO_PATH, normalize_path(path_value)), engine="python", encoding='ISO-8859-1')

                try:
                    setattr(self, key, value)
                    del key, value
                except NameError:
                    if ((key != "L_BASE") & (key != "Y_BASE") & (key != "SCENARIO")):
                        print(f"{key} file is not found.")
                    else:
                        pass
            
        reg_id = pd.DataFrame([e for e in self.COU_ID for i in range(len(self.SEC_ID))]) #type:ignore
        region = pd.DataFrame([e for e in self.COU_NAME for i in range(len(self.SEC_NAME))]) #type:ignore
        sec_id = pd.DataFrame(list(self.SEC_ID) * len(self.COU_ID)) #type:ignore
        sector = pd.DataFrame(list(self.SEC_NAME) * len(self.COU_ID)) #type:ignore

        mrio_list = pd.concat([reg_id, region, sec_id, sector], axis=1)
        mrio_list.columns = ["Reg_ID", "Region", "Sec_ID", "Sector"]
        
        self.mrio_list = mrio_list

        mrio_id = pd.concat([reg_id, sec_id], axis=1)
        mrio_id.columns = ["REG_imp", "PROD_COMM"]
        
        self.mrio_id = mrio_id

        self.A_id = [(a,b) for a,b in zip(
            self.mrio_id["REG_imp"], self.mrio_id["PROD_COMM"])]
            
        output = self.IND_BASE["output"]
        output = output.reset_index()
        output = output.drop(columns=["REG_exp","TRAD_COMM"])
        output = output.drop_duplicates()
        
        self.output = output
        self.POPULATION = pd.melt(self.POPULATION_PROJECTION, id_vars=['Lfd_Nr_agg','Agg_region'], var_name='year')
        self.POPULATION['year'] = pd.to_numeric(self.POPULATION['year'])
        
        print(f"--- Collected exogenous variables: {round(time.time() - start_time, 1)} s ---")
    
    def set_multiyear(self):
        self.MULTIYEAR = True
        return True
    
    def set_inv_converter(self):
        # generate full matrix
        inv_conv = self.INV_CONV #type:ignore 
        inv_conv.columns = ['TRAD_COMM'] + inv_conv.columns[1:].tolist()
        inv_conv = pd.melt(inv_conv, id_vars=['TRAD_COMM'], var_name='PROD_COMM', value_name='input_coeff')
        df_inv_conv = inv_conv[inv_conv['input_coeff']!=0.0].copy()
        a1 = len(df_inv_conv)

        df_inv_conv = pd.concat([df_inv_conv for x in range(len(self.R))])
        df_inv_conv['REG_imp'] = np.repeat(self.R['Region_acronyms'], a1).tolist()

        return df_inv_conv