# -*- coding: utf-8 -*-
"""
Created on Wed Aug  2 10:57:33 2023

@author: wb582890
"""

import os
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import sparse
import pickle
import openpyxl

class results:
    
    def __init__(self, IO_PATH = os.getcwd() + "\\", scenario="BA", country_results=0, iter_results=0, regions=None):
        self.IO_PATH = IO_PATH
        self.country_results = country_results
        self.iter_results = iter_results
        self.scenario = scenario
        self.REGIONS = regions

    def save_change(self, results_dict, year=None):
        if year:
            header_ = (year == 2019)

            with (pd.ExcelWriter(os.path.join(self.IO_PATH, 'GLORIA_results', f'FullResults_{self.scenario}.xlsx'),engine="openpyxl", mode='w') if year == 2019 else
                  pd.ExcelWriter(os.path.join(self.IO_PATH, 'GLORIA_results', f'FullResults_{self.scenario}.xlsx'),engine="openpyxl", mode='a', if_sheet_exists="overlay")) as ResultsWriter:
                book = ResultsWriter.sheets

                for k, v in results_dict.items():
                    df_ = v.copy()
                    if 'year' in df_.columns:
                        df_ = df_.drop(columns=['year'])
                    df_.assign(year=year).to_excel(ResultsWriter, sheet_name=k, startrow=(0 if year == 2019 else book[k].max_row), header=header_)
        else:
            print("ERROR, year was not given for results writer.")
            quit()
            
    
    