# -*- coding: utf-8 -*-
"""
Created on Fri Nov 28 10:11:13 2025

@author: hartv
"""

#%%

"""
MINDSET model main program code
run from command line or SPYDER

if being run from SPYDER that's automatically detected, in that case set input variables where the code says 'SPYDER ARGUMENTS'

if running from CMD you can set input arguments through specifying them in the call, i.e.:
python RunMINDSET.py "IDN_FFSR_onlyHH" "Yes" "GLORIA_results\\baseline_residuals.xlsx"

the arguments in the CMD case are the following
1) [required] scenario_name, this gets read in from GLORIA_template//Scenarios//XXXX.xlsx
2) [optional] recalculate MRIO?, if set to "Yes" or 1, then recalculates Leontieff and Ghoshian matrices
3) [optional] residual file, provide a residual file (empty scenario result) that should be subtracted from calculated results;
            note that the residuals are subtracted at the end of every year

note: output file will be GLORIA_results\\FullResults_XXXX.xlsx

"""
#%%
#region 1_Read_in_data_and_arguments [rgba(231,76,60,0.10)]
#region desc [rgba(231,76,60,0.60)]\
# ^w    [1] READ IN PACKAGES, ARGUMENTS AND DATA
# ^w        this part reads in the relevant external packages (i.e., numpy, pandas, etc) and internal modules stored in SourceCode
# ^w        (i.e., exog_vars, scenario, etc.), it also reads in arguments that can be provided through the command line interface (see above) 
# this 
#endregion

import os

os.system("title MSET-v0.1.1-alpha")
print(" ")
print(">>> MSET [Version v0.1.1-alpha]")
print(">>> Model of Structural Economic Transformation")
print(">>> Starting ... ")
print(" ")
print(" ")

#region 1.1_Read_in_packages [rgba(231,76,60,0.1)]
#region desc [rgba(231,76,60,0.60)]\
# ^w    [1.1] READ IN PACKAGES
#endregion

import numpy as np
import pandas as pd
import time
import sys
import gc
import re
import pickle
import dill
from pathlib import Path
import json
import datetime

from SourceCode.model_class import ModelRun

import warnings


# Instantiate the run
model = ModelRun()

model.run()
