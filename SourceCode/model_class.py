# -*- coding: utf-8 -*-
"""
Created on Fri Nov 28 08:52:34 2025

@author: hartv
"""

#%%
"""
=========================================
model_class.py
=========================================

ModelRun class: MINDSET model main program code
################################################

If running from CMD you can set input arguments through specifying them in the call, i.e.:
python RunMINDSET.py "IDN_FFSR_onlyHH" "Yes" "GLORIA_results\\baseline_residuals.xlsx"

the arguments in the CMD case are the following
1) [required] scenario_name, this gets read in from GLORIA_template//Scenarios//XXXX.xlsx
2) [optional] recalculate MRIO?, if set to "Yes" or 1, then recalculates Leontieff and Ghoshian matrices
3) [optional] residual file, provide a residual file (empty scenario result) that should be subtracted from calculated results;
            note that the residuals are subtracted at the end of every year

note: output file will be GLORIA_results\\FullResults_XXXX.xlsx

This code puts together all individual modules and elements of the model, all individual scripts are imported here.
The 'ModelRun' class shows step-by-step the order of modules as they are being solved.

The 'ModelRun' class includes the following functions:
    - __init__
        Instantiate model run object.
    - run
        Solve model run and save results.
    - solve_year
        Solve model for a specific year.

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
import configparser

from SourceCode.exog_vars import exog_vars
from SourceCode.scenario import scenario
from SourceCode.ener_elas import ener_elas 
from SourceCode.ener_balance import ener_balance
from SourceCode.tax_rev import tax_rev as tax_rev_mod
from SourceCode.BTA import BTA
from SourceCode.prod_cost import prod_cost
from SourceCode.InputOutput import IO
from SourceCode.price import price
from SourceCode.household import household as hh
from SourceCode.government import gov
from SourceCode.trade import trade
from SourceCode.investment import invest
from SourceCode.employment import empl
from SourceCode.income import income
from SourceCode.GDP import GDP
from SourceCode.results import results
from SourceCode.variables import variables_table
from SourceCode.normal_output import normal_output_mod
from SourceCode.ftt_power import solve_year_ftt
from SourceCode.cost_curves import cost_curves
from SourceCode.utils import temporary_storage
from SourceCode.utils import logging
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df, MRIO_mat_to_df
from SourceCode.initiate_modules import initiate_modules
from MINDSET_FTT_Power.SourceCode.model_class import ModelRun as ftt

import warnings




#region 1.1_Read_in_packages [rgba(231,76,60,0.1)]
#region desc [rgba(231,76,60,0.60)]\
# ^w    [1.1] READ IN PACKAGES
#endregion



class ModelRun:
    """
    Class to run the MINDSET model.

    Class object is a single run of the model.

    Local library imports:

        - `Exogenous variables <exog_vars.html>`__
            This class collects all the exogenous variables.
        - `Scenario Module <scenario.html>`__
            This class collects the policy scenario assumptions. 
        - `Input Output Module <InputOutput.html>`__
            This class used to reconstruct new Input-Output (IO) matrices and calculate 
            output changes from new IO matrix and Final Demand (FD) vectors.         
        - `Household Module <household.html>`__
            This class collects the variables and parameters related to households and calculates household prices,
            and changes in prices and income.
        - `Government Module <government.html>`__
            This class collects the variables and parameters related to government and calculates government share in trade,
            demand and spending, and changes in demand and spending.
        - `Employment Module <employment.html>`__
            This class collects the variables and parameters related to employment and calculates base employment,
            employment constraints, and employment changes.
        - `Investment Module <investment.html>`__
            This class collects the variables and parameters related to investment and calculates investment shares,
            induced investment, recycled investment,. and exogenous investment.
        - `GDP Module <employment.html>`__
            This class collects the variables and parameters related to GDP and calculates base GVA
            and GVA changes
        - `Price Module <price.html>`__
            This class collects the variables and parameters related to prices and calculates 
            prices based on exogenous costs.
        - `Border Trade Adjustment (BTA) <BTA.html>`__
            This class collects the variables and parameters related to BTA and calculates 
            border trade adjustments based on exogenous costs.
        - `Trade <trade.html>`__
            This class collects the variables and parameters related to trade and calculates 
            GDP and price dynamics, and applies elasticities to FD and trade IO coefficients.
        - `Income <income.html>`__
            This class collects the variables and parameters related to income and calculates wage and labour compensation,
            and changes in labour compensation, and household and non-residential energy flows.
        - `Energy Balances <ener_balance.html>`__
            This class collects the variables and parameters related to energy balances and emissions and calculates energy flows,
            energy and emissions intensities, energy substitution and emissions by actor.

        Support functions:

        - `Input functions <input_functions.html>`__
            Collection of functions to read in the inputs required to run
            OWEM.


    Attributes
    -----------
    name: str
        Name of model run, and specification file read.
    hist_start: int
        Starting year of the historical data.
    model_start: int
        First year of model timeline.
    model_end: int
        Final year of model timeline.
    current: int
        Current/active year of solution.
    years: tuple of (int, int)
        Bookend years of model_timeline.
    fd_sectors: list of str
        Final demand sectors to solve endogenously (otherwise spec set to
        exogenous).
    st_sectors: list of str
        Supply and transformation sectors to solve endogenously (otherwise spec
        set to exogenous).
    timeline: list of int
        Years of the model timeline.
    time_sim_index: list of int
        Index values of simulation years from model timeline.
    time_lags: dict of {int: dict of {str: numpy.ndarray}}
        Lagged values (in previous years of solution).
    output: dict of {str: numpy.ndarray}
        Dictionary containing all model variables for output.
    run_modules: dict of {str: boolean}
        Dictionary of booleans for active modules to run
    log: dict of {str: list}
        Contains any warnings in order to populate a logfile afterwards for the
        user's benefit.

    Methods
    -----------
    run
        Solve model run and save results.
    solve_year
        Solve model for a specific year.
    """
    
    
    def __init__(self):

        # read in the arguments here
        self.settingsini = False
        if len(sys.argv) > 1:
            self.settingsini = sys.argv[1]
        
        # Attributes given in settings.ini file
        config = configparser.ConfigParser()
        if self.settingsini:
            config.read(f'{self.settingsini}')
        else:
            config.read('s_base.ini')

        self.scenario_name = config.get('settings', 'scenario_name')
        self.model_start = int(config.get('settings', 'model_start'))
        self.model_end = int(config.get('settings', 'model_end'))
        # define years to run the model for
        self.years = np.arange(self.model_start, self.model_end + 1)
        # ! keep TRUE unless want to turn-off within year iter
        self.SWITCH_WITHIN_YEAR_LOOP = config.getboolean('settings', 'SWITCH_WITHIN_YEAR_LOOP')
        self.mrio_inverse_recalculate = config.getboolean('settings', 'mrio_inverse_recalculate')
        # TODO these are possibilities to store tax_incidence or dL_ener in file if they are not changing between scenarios
        # TODO these are NOT currently used
        self.tax_incidence_file = str(config.get('settings', 'tax_incidence_file'))    
        self.dL_ener_file = str(config.get('settings', 'dL_ener_file')) 
        # TODO check whether / how this is still relevant?
        self.bta = int(config.get('settings', 'bta'))
        self.CALIBRATING = config.getboolean('settings', 'CALIBRATING')
        self.ftt_run = config.getboolean('settings', 'ftt_run')
        print(f"FTT run is set to {self.ftt_run}")

        self.COND_LABOR = int(config.get('settings','COND_LABOR')) / 100
        self.COND_TAX = int(config.get('settings','COND_TAX')) / 100
        self.COND_TRADE = int(config.get('settings','COND_TRADE')) / 100
        self.COND_PRICE = int(config.get('settings','COND_PRICE')) / 100
        self.ITER_MAX = int(config.get('settings','ITER_MAX'))

        self.WRITE_AT_END = config.getboolean('settings', 'WRITE_AT_END')
        
        self.ftt_model = None

        # TODO move it from here
        self.cost_curve_employment = [24,25,26]
        self.refining_sectors = [62,63,94]
        
        # SPYDER = 'SPY_PYTHONPATH' in os.environ
                

        #endregion
        
        #region 1.2_Initialize_logging [rgba(231,76,60,0.15)]
        #region desc [rgba(231,76,60,0.60)]\
        # ^w    [1.2] Initialize logging and disable warnings
        # ^w        two types of warnings are disabled: FutureWarning and UserWarnings
        # 
        # TODO  we might eventually want to remove / rewrite stuff that causes warnings to be raised
        #endregion
        

        self.Log = logging()
        self.V = variables_table(self.Log, self.scenario_name, self.model_start, self.model_end)
        
        
        warnings.simplefilter(action='ignore', category=FutureWarning)
        warnings.simplefilter(action='ignore', category=UserWarning)
        warnings.simplefilter(action='ignore', category=RuntimeWarning)
        
        #endregion
        
        #region 1.3_Read_arguments [rgba(231,76,60,0.15)]
        #region desc [rgba(231,76,60,0.60)]\
        # ^w    [1.3] Read in command line arguments
        # ^w        see above as well
        # ^w        if running in SPYDER then arguments than arguments need to be set where the code says 'SPYDER ARGUMENTS'
        # ^w        
        # ^w        otherwise CMD arguments are the following
        # ^w        1) [required] scenario_name, this gets read in from GLORIA_template//Scenarios//XXXX.xlsx
        # ^w        2) [optional] recalculate MRIO?, if set to "Yes" or 1, then recalculates Leontieff and Ghoshian matrices
        # ^w        3) [optional] residual file, provide a residual file (empty scenario result) that should be subtracted from calculated results;
        # ^w            note that the residuals are subtracted at the end of every year
        # ^w
        # ^w        note: output file will be GLORIA_results\\FullResults_XXXX.xlsx
        #endregion
        
        
        # CATCH if no SCENARIO provided or if SCENARIO file does not exists
        
        if self.scenario_name is None:
            os.system('color 4')
            print("######################################################################################")
            print("!!!! ERROR: No scenario provided. In CMD mode you need to provide a scenario to run!")
            print("######################################################################################")
            print("Exiting.")
            os.system('color')
            quit()
        
        cwd_ = os.getcwd()
        self.scenario_path = os.path.join(cwd_, "Data", "MSET_data", "Scenarios", f"{self.scenario_name}.xlsx")
        if not (os.path.isfile(self.scenario_path)):
            os.system('color 4')
            print("")
            print("######################################################################################")
            print("!!!! ERROR: Scenario file not found!")
            print("!!!! NOT FOUND: {}".format(self.scenario_path))
            print("######################################################################################")
            print("Exiting.")
            os.system('color')
            quit()
        
        print("######################################################################################")
        print("Scenario being run is: {}".format(self.scenario_name))
        print("######################################################################################")
        print("")
        #endregion
        
        #region 1.4_Setup_timer_and_stuff [rgba(231,76,60,0.15)]
        #region desc [rgba(231,76,60,0.60)]\
        # ^w    [1.4] Setup model timer and stuff
        # ^w        start_time will store the start time and subtracting from time at the end will tell us the model run-time
        # ^w        temp will create the 'Temp' folder and allows us to store stuff temporarily there and delete once the model exists
        # ^w
        # ^w        EXOG_VARS is where we store external data, it is an instance of the exog_vars class
        # ^w        it reads in external data as specified in the GLORIA_template\\Variables\\Variable_list_MINDSET.xlsx file
        #endregion
        
        self.start_time = time.time()
        self.module_time = time.time()
        self.temp = temporary_storage("Temp")

        
        # INITIALIZE exogenous variables (excluding scenario variables)
        self.EXOG_VARS = exog_vars()
        self.EXOG_VARS.set_multiyear()
        
        self.MRIO_df_to_vec_DEF = lambda df,name: MRIO_df_to_vec(df, 'REG_imp','PROD_COMM',name, self.EXOG_VARS.R_list, self.EXOG_VARS.P_list)
        self.MRIO_df_to_vec_DEF_1 = lambda df,name: MRIO_df_to_vec(df, 'REG_imp','PROD_COMM',name, self.EXOG_VARS.R_list, self.EXOG_VARS.P_list, default_value=1)
        
        self.MRIO_vec_to_df_DEF = lambda vec,name: MRIO_vec_to_df(vec, name, len(self.EXOG_VARS.P), self.EXOG_VARS.R)\
                        .rename(columns={'target-sector':'PROD_COMM','target-country-iso3':'REG_imp'}).drop(columns=['target-country'])
        
        

        
        #endregion
        #endregion
        
        #%%
        # Setup FTT:Power

        if self.ftt_run:
            
            # Instantiate the run
            self.ftt_model = ftt()
            
            # Call solve_year method for each year while MINDSET is not started
            self.ftt_model.ftt_start = min(self.ftt_model.timeline)
            mindset_start = min(self.years)
            setup_years = np.arange(self.ftt_model.ftt_start, mindset_start)
            self.ftt_model.ftt_fuel_converter = pd.read_csv('MINDSET_FTT_Power/Utilities/ftt_to_mindset_fuels.csv')
            self.ftt_model.ftt_tech_converter = pd.read_csv('MINDSET_FTT_Power/Utilities/ftt_to_mindset_technology.csv')
            self.ftt_model.ftt_inv_converter = pd.read_csv('MINDSET_FTT_Power/Utilities/ftt_technology_investment_converter.csv')
            self.ftt_model.ftt_inv_converter = self.ftt_model.ftt_inv_converter.set_index('PROD_COMM')
            self.ftt_model.investment = dict()
            
            for y, year in enumerate(setup_years):
                # Solve year
                self.ftt_model.variables, self.ftt_model.lags = self.ftt_model.solve_year(year, y, self.ftt_model.scenarios)
                
                # Populate output container
                for var in self.ftt_model.variables:
                    if 'TIME' in self.ftt_model.dims[var]:
                        self.ftt_model.output[self.ftt_model.scenarios][var][:, :, :, y] = self.ftt_model.variables[var]
                    else:
                        self.ftt_model.output[self.ftt_model.scenarios][var][:, :, :, 0] = self.ftt_model.variables[var]
                    
                # Assess investment
                # Calculate changes in investment
                self.ftt_model.investment[year] = (np.array(self.ftt_model.ftt_inv_converter[list(self.ftt_model.titles['T2TI'])])[np.newaxis, :, :] * 
                              self.ftt_model.output[self.ftt_model.scenarios]['MWIY'][:, :, 0, y][:, np.newaxis, :]).sum(axis = 2)
                # Convert mEUR 2010 to mUSD 2010 and then to mUSD 2019
                self.ftt_model.investment[year] = self.ftt_model.investment[year] * 1.33 * 1.17

        
        
        #%%
        
        #region 2_Solving_the_model [rgba(52,152,219,0.10)]
        #region desc [rgba(52,152,219,0.6)]
        # ^w    [2] Solving the model - year-by-year (YbY) and within year (wY) iterations
        # ^w        this part is the core of the model, we first set up dynamic variables then go into the YbY and wY iterations
        # ^w        this means two loops, one embedded, there is a year loop [2.2], within which we have a [2.2.2] within year loop
        #endregion
        
        
        #region 2.1_Define_dynamic_variables [rgba(52,152,219,0.15)]
        #region desc [rgba(52,152,219,0.6)]
        # ^w    [2.1] Define dynamic variables 
        # ^w        that are carried over across the year YbY
        #endregion
        
        # ! variables outside of loop (dynamic)
        self.DYNAMIC = {
            "dy_inv_induced_L1": np.zeros((len(self.EXOG_VARS.R)*len(self.EXOG_VARS.P))), #type:ignore
            'inv_induced_L1': pd.DataFrame(columns=['TRAD_COMM','PROD_COMM','REG_imp','REG_exp','dy']),
            'output': {}, # 2-dimensional (countryXsector), output, '000 USD constant price (base start year)
            'value_added': {}, # value added components, '000 USD current price
            'calibration_error': {},
            'government_spending_by_revenue_source': pd.DataFrame(),
            'govt_spending_delta': pd.DataFrame(),
            'other_country_vars': pd.DataFrame(),
            'tax_rate_prev': pd.DataFrame(columns=['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','delta_tax']),
            'tax_rate_hh_prev': pd.DataFrame(columns=['REG_imp','PROD_COMM','TRAD_COMM','REG_exp','delta_tax_hh']),
            'residual_consumption_hh': pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','VIPA']),
            'residual_consumption_fcf': pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','VDFA']),
            'residual_consumption_gov': pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','VIGA']),
            'carbon_content': pd.DataFrame(),
            'carbon_content_process': pd.DataFrame(),
            'HH_price': {},
            'carbon_tax_revenues': {},
            'investment_converter': pd.DataFrame(),
            'interest_rate_adjust': pd.DataFrame(),
            'dq_exog_hh_prev': np.zeros((len(self.EXOG_VARS.R)*len(self.EXOG_VARS.P))),
            'dq_exog_fcf_prev': np.zeros((len(self.EXOG_VARS.R)*len(self.EXOG_VARS.P))),
            'dq_exog_gov_prev': np.zeros((len(self.EXOG_VARS.R)*len(self.EXOG_VARS.P))),
            'dq_supply_constraint_no_empl': np.zeros((len(self.EXOG_VARS.R)*len(self.EXOG_VARS.P))),
            'fuel_price': pd.DataFrame(),
            'cbam_incidence': {}
        }
        
        self.DYNAMIC['PROJECTION_OUTPUT'] = self.EXOG_VARS.PROJECTION_OUTPUT
        
        # ! might need to move later
        projections = self.EXOG_VARS.PROJECTION_OUTPUT.copy()
        projections = pd.melt(projections, id_vars=['REG_imp','PROD_COMM'], var_name='year')
        df = projections.copy()
        df['g'] = df['value'] / df.groupby(['REG_imp','PROD_COMM'])['value'].transform('shift')
        df = df.groupby(['REG_imp','PROD_COMM']).agg({"g":'mean'}).reset_index()
        self.initial_g = self.MRIO_df_to_vec_DEF(df, 'g')
        # import pdb; pdb.set_trace()
        
        projections = projections[~projections['value'].isna()]
        projections['value_lagged'] = projections.groupby(['REG_imp','PROD_COMM'])['value'].shift(1)
        projections['g'] = projections['value'] / projections['value_lagged']
        projections = projections[~projections['g'].isna()]
        df['year'] = "2019"
        projections = pd.concat([df, projections])
        
        self.DYNAMIC['PROJECTION_OUTPUT'] = projections[['REG_imp','PROD_COMM','year','g']].copy()
        
        #endregion
        
        #region 2.2_Year-by-Year_loop [rgba(52,152,219,0.15)]
        #region desc [rgba(52,152,219,0.6)]
        # ^w    [2.2] Year-by-year loop
        # ^w        every iteration is a single year with dynamic variables defined in [2.1] carried over as starting values to the next year
        #endregion
        
    def run(self):
        
        for year in self.years:
            os.system("title MSET-v0.1.1-alpha - {}".format(year))
            if self.ftt_model is None:
                self.DYNAMIC, self.EXOG_VARS, self.CALIBRATING, self.MRIO_df_to_vec_DEF, \
                                    self.MRIO_vec_to_df_DEF, self.ftt_model, self.Log = self.solve_year(year, self.DYNAMIC, self.EXOG_VARS, 
                                                                                                        self.CALIBRATING, self.MRIO_df_to_vec_DEF, 
                                                                                                        self.MRIO_vec_to_df_DEF, self.Log, ftt_model=None)
            else:
                self.DYNAMIC, self.EXOG_VARS, self.CALIBRATING, self.MRIO_df_to_vec_DEF, \
                    self.MRIO_vec_to_df_DEF, self.ftt_model, self.Log = self.solve_year(year, self.DYNAMIC, self.EXOG_VARS, 
                                                                                        self.CALIBRATING, self.MRIO_df_to_vec_DEF, 
                                                                                        self.MRIO_vec_to_df_DEF, self.Log, ftt_model=self.ftt_model)
            
        print("")
        total_runtime = time.time() - self.start_time
        print("--- Model run: %s seconds ---" % round(total_runtime, 1))
        
        # for k, v in io_aggregate_time.items():
        #     fractime = v / total_runtime * 100
        #     print("Function {k} took {v:.2f} seconds ({fractime:.2f} percent)")


    def solve_year(self, year, DYNAMIC, EXOG_VARS, CALIBRATING, MRIO_df_to_vec_DEF, MRIO_vec_to_df_DEF, Log, ftt_model=None):
        
        print("###########################################")
        print(f"###              {year}                ###")
        print("###########################################")
    
        year_time = time.time()
    
        CALIBRATION_VARS = {
            'residual_fd_hh': pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','VIPA']),
            'residual_fd_hh_prev': pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','VIPA']),
            'residual_fd_gov': pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','VIGA']),
            'residual_fd_gov_prev': pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','VIGA']),
            'residual_fd_fcf': pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','VDFA']),
            'residual_fd_fcf_prev': pd.DataFrame(columns=['REG_exp','REG_imp','TRAD_COMM','VDFA']),
            'iter0_y': np.zeros((len(EXOG_VARS.R)*len(EXOG_VARS.P))),
            'check_sector': np.zeros((len(EXOG_VARS.R)*len(EXOG_VARS.P))),
            'country_check_prev': np.inf,
            'calibrated_w_errors': False,
            'dynamic': None
        }
    
        if (not CALIBRATING):
            try:
                with open(os.path.join("Residuals", f"residuals_{year}.pkl"), 'rb') as handle:
                    residuals = pickle.load(handle)
                CALIBRATION_VARS['residual_fd_hh'] = residuals['residual_consumption_hh']
                CALIBRATION_VARS['residual_fd_gov'] = residuals['residual_consumption_gov']
                CALIBRATION_VARS['residual_fd_fcf'] = residuals['residual_consumption_fcf']
                DYNAMIC['residual_consumption_hh'] = residuals['residual_consumption_hh']
                DYNAMIC['residual_consumption_gov'] = residuals['residual_consumption_gov']
                DYNAMIC['residual_consumption_fcf'] = residuals['residual_consumption_fcf']
            except EOFError:
                pass
            except FileNotFoundError:
                # if there are no residuals files, but there is no calibration, then do ENDO run
                pass
    
        if CALIBRATING:
            calibration_counter = 0
        else:
            calibration_counter = 1
    
        if CALIBRATING:   
            print(">>>>>>>>> CALIBRATING")
            CALIBRATION_RUNNING = True
            ERROR = False
            while CALIBRATION_RUNNING:
                # ! CALIBRATION LOOP

                Scenario, HH_model, GOV_model, INV_model, IO_model, Inc_model, Empl_model, \
                    HH_price, HH_price_eff, HH_inc_eff, HH_tech_substitution, GOV_recyc, Prod_cost, \
                    INV_CONV, ener_base, dp_trade, dq_total, A_iochange, fd_trade_response, dp_ctax, \
                    supply_constraint, supply_constraint_no_empl, dlabor_sec, profit_rate_mean_L1, \
                    dq_supply_constraint, dq_supply_constraint_no_empl, dq_tech_eff, dq_trade_eff, \
                    dq_trade_hh, dq_trade_gov, dq_trade_fcf, dq_hh_price, dq_hh_inc, dq_hh_save, dq_hh_exog, dq_gov_recyc, \
                    dq_gov_delta, dq_inv_induced, dq_inv_recyc, dq_inv_exog, dq_hh_exog_fd, \
                    dq_fcf_exog_fd, dq_gov_exog_fd, dq_calibration_residual, \
                    dq_structural_change, dq_hh_tech_substitution, dq_io_change = initiate_modules(self, DYNAMIC, EXOG_VARS, MRIO_df_to_vec_DEF,
                                                                                                                   MRIO_vec_to_df_DEF, CALIBRATING, CALIBRATION_VARS,
                                                                                                                   year, Log, calibration_counter, self.V, ftt_model=ftt_model)

                # ? GDP
                projected_q = MRIO_df_to_vec(DYNAMIC['PROJECTION_OUTPUT'].pipe(lambda d: d[d['year']==str(year)]).drop(columns=['year']), 'REG_imp','PROD_COMM', 'g', EXOG_VARS.R_list, EXOG_VARS.P_list)
                projected_q = self.V.read_var("output", year-1) * projected_q
                residual_q = projected_q - self.V.read_var("output", year-1) - dq_total 

                # ! exclude cost curve sectors
                residual_df = MRIO_vec_to_df_DEF(residual_q, 'residual_q')
                residual_df.loc[residual_df['PROD_COMM'].isin(self.cost_curve_employment), 'residual_q'] = 0.0
                residual_q = MRIO_df_to_vec_DEF(residual_df, 'residual_q')

                # ! exclude small values
                residual_q[np.abs(residual_q) < 10] = 0.0

                check = np.nan_to_num(residual_q / projected_q, posinf=0, neginf=0, nan=0)
                check_country = np.nan_to_num(residual_q).reshape(-1, len(EXOG_VARS.P_list)).sum(axis=1) / np.nan_to_num(projected_q).reshape(-1, len(EXOG_VARS.P_list)).sum(axis=1)
                check_country = np.nan_to_num(check_country)
        
                DYNAMIC['calibration_error'] = MRIO_vec_to_df_DEF(residual_q, "residual_q")
                
                print("CALIBRATION                       iteration #{}".format(calibration_counter))
        
                print(MRIO_vec_to_df(check,'% diff',len(EXOG_VARS.P_list),EXOG_VARS.R).sort_values(by="% diff"))
                print("CALIBRATION                       Mean abs diff per sector: {}".format(np.mean(np.abs(check))))
                print("CALIBRATION                       Max abs diff by country: {}".format(np.max(np.abs(check_country))))
                print("CALIBRATION                       Prev iteration: {}".format(CALIBRATION_VARS['country_check_prev']))
        
                # max diff in sector 10%, max diff in country 1%
                if (((np.max(np.abs(check_country)) < 0.02) & (np.mean(np.abs(check)) < 0.10) & (calibration_counter > 0)) | (ERROR == True)):
                    # ???????????????????????????????
                    # ? CALIBRATED SUCCESS
                    # ???????????????????????????????
                    CALIBRATION_RUNNING = False
                    DYNAMIC['residual_consumption_hh'] = CALIBRATION_VARS['residual_fd_hh']
                    DYNAMIC['residual_consumption_fcf'] = CALIBRATION_VARS['residual_fd_fcf']
                    DYNAMIC['residual_consumption_gov'] = CALIBRATION_VARS['residual_fd_gov']
                    print("CALIBRATION                       Calibration done.")
                    break
        
                if (np.max(np.abs(check_country)) > CALIBRATION_VARS['country_check_prev'])  & (calibration_counter > 0):
                    # ???????????????????????????????
                    # ? NON-convergence
                    # ???????????????????????????????
                    # with open("Temp//all_vars.pkl", "rb") as f:
                    #     loaded_vars = dill.load(f)
                    #     locals().update(loaded_vars)

                    CALIBRATION_VARS['residual_fd_hh'] = CALIBRATION_VARS['residual_fd_hh_prev']
                    CALIBRATION_VARS['residual_fd_gov'] = CALIBRATION_VARS['residual_fd_gov_prev']
                    CALIBRATION_VARS['residual_fd_fcf'] = CALIBRATION_VARS['residual_fd_fcf_prev']
        
                    # CALIBRATION_RUNNING = False
                    ERROR = True
        
                    # DYNAMIC['residual_consumption_hh'] = CALIBRATION_VARS['residual_fd_hh']
                    # DYNAMIC['residual_consumption_fcf'] = CALIBRATION_VARS['residual_fd_fcf']
                    # DYNAMIC['residual_consumption_gov'] = CALIBRATION_VARS['residual_fd_gov']
        
                    # print(MRIO_vec_to_df(check,'% diff',len(EXOG_VARS.P_list),EXOG_VARS.R).sort_values(by="% diff"))
                    # print("CALIBRATION                       Mean abs diff per sector: {}".format(np.mean(np.abs(check))))
                    # print("CALIBRATION                       Mean abs diff by country: {}".format(np.max(np.abs(check_country))))
                    print("CALIBRATION                       Calibration did not converge, errors saved.")
                    continue
        
                # ? [0.5] multiplier has been added to get rid of oscillation behaviour in calibration
                # ? this decreases steps so more smooth calibration 
                fd_vec = IO_model.calc_fd_vec(residual_q, IO_model.y0) * 0.5
                
                #%%
                # TODO all should be in modules!
                # List of variable names you want to save
                list_ = [x for x in locals().keys() if x.startswith(("dp_","dgdp_","dq_"))]
                vars_ = ['A_iochange','A_trade','HH_price_eff','HH_inc_eff','HH_tech_substitution','GOV_recyc','fd_trade_response','profit_rate_mean_L1','dlabor_sec',
                         'supply_constraint','supply_constraint_no_empl']
                modules_ = ['EXOG_VARS', 'DYNAMIC', 'CALIBRATION_VARS','Scenario','Energy_emissions','GDP_model','Inc_model',"INV_model",'IO_model','GOV_model',
                            'Prod_cost','HH_model']
                to_save = list_ + vars_ + modules_
                safe_vars = {name: locals()[name] for name in to_save if name in locals()}
        
                with open(os.path.join("Temp","all_vars.pkl"), "wb") as f:
                    dill.dump(safe_vars, f)
        
                # make sure that residual does not cause negative consumption
                # fd_vec[(fd_vec + IO_model.y0) < 0] = 0
        
                CALIBRATION_VARS['country_check_prev'] = np.max(np.abs(check_country))
        
                fd_df = MRIO_vec_to_df(fd_vec, 'residualFD', len(EXOG_VARS.P), EXOG_VARS.R)\
                .rename(columns={'target-country-iso3':'REG_exp','target-sector':'TRAD_COMM'}).drop(columns=['target-country'])
        
                hh_cons = HH_model.HH.reset_index() # VIPA
                fcf_cons = INV_model.FCF.reset_index() # VDFA
                gov_cons = GOV_model.GOV[['REG_imp','REG_exp','TRAD_COMM','VIGA']] # VIGA
        
                cons = hh_cons.merge(fcf_cons, how='outer').merge(gov_cons, how='outer').fillna(0)
                cons['total'] = cons['VIGA'] + cons['VIPA'] + cons['VDFA']
                cons['gov_share'] = cons['VIGA'] / cons['total']
                cons['hh_share'] = cons['VIPA'] / cons['total']
                cons['fcf_share'] = cons['VDFA'] / cons['total']
        
                fd_df = cons.merge(fd_df, how='left', on=['REG_exp','TRAD_COMM'])
                fd_df['total_row'] = (fd_df['total'] / fd_df.groupby(['REG_exp','TRAD_COMM'])['total'].transform('sum')) * fd_df['residualFD']
        
                fd_df['VIPA_new'] = fd_df['total_row'] * fd_df['hh_share']
                fd_df['VIGA_new'] = fd_df['total_row'] * fd_df['gov_share']
                fd_df['VDFA_new'] = fd_df['total_row'] * fd_df['fcf_share']
        
                # make sure that consumption per row doesn't go negative
                fd_df.loc[(fd_df['VIGA_new'] + fd_df['VIGA']) < 0.0, 'VIGA_new'] = fd_df.loc[(fd_df['VIGA_new'] + fd_df['VIGA']) < 0.0, 'VIGA'] * -0.9
                fd_df.loc[(fd_df['VIPA_new'] + fd_df['VIPA']) < 0.0, 'VIPA_new'] = fd_df.loc[(fd_df['VIPA_new'] + fd_df['VIPA']) < 0.0, 'VIPA'] * -0.9
                fd_df.loc[(fd_df['VDFA_new'] + fd_df['VDFA']) < 0.0, 'VDFA_new'] = fd_df.loc[(fd_df['VDFA_new'] + fd_df['VDFA']) < 0.0, 'VDFA'] * -0.9
        
                fd_df = fd_df.drop(columns=['VIPA','VIGA','VDFA']).rename(columns={'VIGA_new':'VIGA','VIPA_new':'VIPA','VDFA_new':'VDFA'})
        
                fd_hh = fd_df[['REG_exp','REG_imp','TRAD_COMM','VIPA']].set_index(['REG_exp','REG_imp','TRAD_COMM'])
                fd_gov = fd_df[['REG_exp','REG_imp','TRAD_COMM','VIGA']].set_index(['REG_exp','REG_imp','TRAD_COMM'])
                fd_fcf = fd_df[['REG_exp','REG_imp','TRAD_COMM','VDFA']].set_index(['REG_exp','REG_imp','TRAD_COMM'])
        
                CALIBRATION_VARS['residual_fd_hh_prev'] = CALIBRATION_VARS['residual_fd_hh'].copy()
                CALIBRATION_VARS['residual_fd_gov_prev'] = CALIBRATION_VARS['residual_fd_gov'].copy()
                CALIBRATION_VARS['residual_fd_fcf_prev'] = CALIBRATION_VARS['residual_fd_fcf'].copy()
                CALIBRATION_VARS['residual_fd_hh'] = fd_hh
                CALIBRATION_VARS['residual_fd_gov'] = fd_gov
                CALIBRATION_VARS['residual_fd_fcf'] = fd_fcf
        
                calibration_counter += 1
        
        else:
            print(">>>>>>>>> NOT CALIBRATING")
            Scenario, HH_model, GOV_model, INV_model, IO_model, Inc_model, Empl_model, \
                HH_price, HH_price_eff, HH_inc_eff, HH_tech_substitution, GOV_recyc, Prod_cost, \
                INV_CONV, ener_base, dp_trade, dq_total, A_iochange, fd_trade_response, dp_ctax, \
                supply_constraint, supply_constraint_no_empl, dlabor_sec, profit_rate_mean_L1, \
                dq_supply_constraint, dq_supply_constraint_no_empl, dq_tech_eff, dq_trade_eff, \
                dq_trade_hh, dq_trade_gov, dq_trade_fcf, dq_hh_price, dq_hh_inc, dq_hh_save, dq_hh_exog, dq_gov_recyc, \
                dq_gov_delta, dq_inv_induced, dq_inv_recyc, dq_inv_exog, dq_hh_exog_fd, \
                dq_fcf_exog_fd, dq_gov_exog_fd, dq_calibration_residual, \
                dq_structural_change, dq_hh_tech_substitution, dq_io_change = initiate_modules(self, DYNAMIC, EXOG_VARS, MRIO_df_to_vec_DEF,
                                                                                                                   MRIO_vec_to_df_DEF, CALIBRATING, CALIBRATION_VARS,
                                                                                                                   year, Log, calibration_counter, self.V, ftt_model=ftt_model)
    # let's remove calibration errors going forward to not have compounding issues
    # MRIO_df_to_vec(EXOG_VARS.PROJECTION_OUTPUT, 'REG_imp','PROD_COMM', str(year), EXOG_VARS.R_list, EXOG_VARS.P_list)
    # !!!! could be problematic if order changes!
    
        if CALIBRATING:
            # DYNAMIC['PROJECTION_OUTPUT'][[str(x) for x in years if x > year]] = \
                # DYNAMIC['PROJECTION_OUTPUT'][[str(x) for x in years if x > year]].apply(lambda x: x - DYNAMIC['calibration_error']['residual_q'].values, axis=0)
            pd.DataFrame.from_dict(DYNAMIC['calibration_error']).to_csv(os.path.join("Residuals", f"calibration_errors_{year}.csv"))
            # ! write residuals to pickle
    
            residuals_obj = {
                'residual_consumption_hh': DYNAMIC['residual_consumption_hh'],
                'residual_consumption_fcf': DYNAMIC['residual_consumption_fcf'],
                'residual_consumption_gov': DYNAMIC['residual_consumption_gov']
            }
    
            with open(os.path.join("Residuals","residuals_{}.pkl".format(year)), 'wb') as handle:
                pickle.dump(residuals_obj, handle, protocol=pickle.HIGHEST_PROTOCOL)
    
        #region 3_Final_results_calc_and_print [rgba(155,89,182,0.10)]
        #region desc [rgba(155,89,182,0.60)]
        # ^w    [3] CALCULATING FINAL RESULTS and PRINTING
        # ^w        these calculations are done after the iterations, therefore mostly 'static'
        # ^w
        # TODO  currently includes GDP calculation which might not be right?
        #endregion
    
        #region 3.2.1_Price_index [rgba(155,89,182,0.25)]
        #region desc [rgba(155,89,182,0.60)]
        # ^w    [3.2.1] Calculate price index (cumulative over time)
        #endregion
        dyn_price = self.V.read_var("dp_all", year, as_df=True)
        self.V.write_var('delta_price_yoy', year, self.V.read_var('dp_all', year))
        if year == self.model_start:
            dyn_price['price_index'] = dyn_price['dp_all'] + 1
            dyn_price = dyn_price.drop(columns=['price_index'])
        # bring in existing price change
        dyn_price = self.V.read_var('price_index', year-1, as_df=True).merge(dyn_price, how='left', on=['REG_imp','PROD_COMM'])
        dyn_price['price_index'] = dyn_price['price_index'] * (1 + dyn_price['dp_all'])
        self.V.write_var('price_index', year, dyn_price.drop(columns=['dp_all']), from_df=True)
    
        # ! random check on strange prices
        if np.min(dyn_price['price_index']) < 0:
            os.system('color 4')
            print("######################################################################################")
            print("!!!! ERROR: We have a price index that's below zero! That's not good.")
            print("######################################################################################")
            import pdb; pdb.set_trace()
            print("Exiting.")
            os.system('color')
            quit()  
    
        price_index = self.V.read_var('price_index', year)
        #endregion
    
        #region desc [rgba(155,89,182,0.60)]
        # ^w    [3.0] Energy calculation
        # ^w
        #endregion
    
        # ener_base = Energy_emissions.calc_fuel_prod_base()
        # DYNAMIC['energy_flows'][year] = ener_base
    
        # [dener_total, dener_tech_eff, dener_trade_eff, dener_trade_hh, dener_trade_gov, dener_trade_fcf, dener_hh_price,
        # dener_hh_inc, dener_gov_recyc, dener_gov_delta, dener_inv_induced, dener_inv_recyc,
        # dener_inv_exog, dener_supply_constraint, dener_hh_exog_fd,  
        # dener_fcf_exog_fd, dener_gov_exog_fd, dener_calibration_residual,
        # dener_structural_change, dener_hh_tech_substitution] = Energy_emissions.calc_fuel_prod_change([dq_total, dq_tech_eff, dq_trade_eff, dq_trade_hh, dq_trade_gov, dq_trade_fcf,
        #                                                        dq_hh_price, dq_hh_inc, dq_gov_recyc, dq_gov_delta,
        #     dq_inv_induced, dq_inv_recyc, dq_inv_exog, dq_supply_constraint, dq_hh_exog_fd,
        #     dq_fcf_exog_fd, dq_gov_exog_fd, dq_calibration_residual, dq_structural_change, dq_hh_tech_substitution], DYNAMIC['output'][year-1])
    
        #region 3.1_GDP_calc [rgba(155,89,182,0.15)]
        #region desc [rgba(155,89,182,0.60)]
        # ^w    [3.1] GDP calculation
        # ^w        calculate GDP as q * (1- A_matrix)
        # ^w
        #endregion
    
        module_time = time.time()
            
        GDP_model = GDP(A_iochange, price_index, self.V.read_var("output", year-1))
        gdp_base = GDP_model.calc_gva_base() # this is GDP at the beginning of the year; constant price
        gdp_base_current = GDP_model.calc_gva_base(type_="current") # this is GDP at the beginning of the year; current price
    
        #! supply constraint effects GDP directly (ie full cost goes to GDP)
        #! but only for direct impacts, non-direct is still only VA part
    
        # dq_total_gdp = dq_total - dq_supply_constraint - dq_supply_constraint_no_empl
        dq_total_gdp = dq_total
    
        # dgdp_empl_LSC
        [dgdp_total, dgdp_tech_eff, dgdp_trade_eff, dgdp_trade_hh, dgdp_trade_gov, dgdp_trade_fcf, dgdp_hh_price,
        dgdp_hh_inc, dgdp_hh_save, dgdp_hh_exog, dgdp_gov_recyc, dgdp_gov_delta, dgdp_inv_induced, dgdp_inv_recyc,
        dgdp_inv_exog, dgdp_hh_exog_fd,  
        dgdp_fcf_exog_fd, dgdp_gov_exog_fd, dgdp_calibration_residual, 
        dgdp_structural_change, dgdp_hh_tech_substitution, dgdp_io_change] = GDP_model.calc_gva_changes([dq_total_gdp, dq_tech_eff, dq_trade_eff, dq_trade_hh, dq_trade_gov, dq_trade_fcf,
                                                               dq_hh_price, dq_hh_inc, dq_hh_save, dq_hh_exog, dq_gov_recyc, dq_gov_delta,
            dq_inv_induced, dq_inv_recyc, dq_inv_exog, dq_hh_exog_fd,
            dq_fcf_exog_fd, dq_gov_exog_fd, dq_calibration_residual, dq_structural_change, dq_hh_tech_substitution, dq_io_change], A_iochange)
            # , dq_empl_labour_supply_constraint], A_trade)
    
        dgdp_total_current = GDP_model.calc_gva_changes(dq_total_gdp, A_iochange, type_="current")
    
        # ! add supply constraint effects
        # ! calc gva from direct impact
        # [d_gdp_supply_constraint, d_gdp_supply_constraint_no_empl] =\
        #      GDP_model.calc_gva_changes([supply_constraint['dq_supply_constraint_direct'],
        #      supply_constraint_no_empl['dq_supply_constraint_direct']], A_iochange)
    
        # [cd_gdp_supply_constraint, cd_gdp_supply_constraint_no_empl] = GDP_model.calc_gva_changes([supply_constraint['dq_supply_constraint_direct'],supply_constraint_no_empl['dq_supply_constraint_direct']], A_iochange, type_="current")
    
        # [i_gdp_supply_constraint, i_gdp_supply_constraint_no_empl] =\
        #      GDP_model.calc_gva_changes([dq_supply_constraint, dq_supply_constraint_no_empl], A_iochange)    
    
        # [ci_gdp_supply_constraint, ci_gdp_supply_constraint_no_empl] =\
        #      GDP_model.calc_gva_changes([dq_supply_constraint, dq_supply_constraint_no_empl], A_iochange, type_="current")   
    
        # dgdp_supply_constraint = dq_supply_constraint + i_gdp_supply_constraint - d_gdp_supply_constraint
        # dgdp_supply_constraint_no_empl = dq_supply_constraint_no_empl + i_gdp_supply_constraint_no_empl - d_gdp_supply_constraint_no_empl 
        
        # cdgdp_supply_constraint = (dq_supply_constraint * MRIO_df_to_vec_DEF(DYNAMIC['price_index'][year], 'price_index')) + ci_gdp_supply_constraint - cd_gdp_supply_constraint
        # cdgdp_supply_constraint_no_empl = dq_supply_constraint_no_empl + ci_gdp_supply_constraint_no_empl - cd_gdp_supply_constraint_no_empl 
        
        # dgdp_total = dgdp_total + dgdp_supply_constraint + dgdp_supply_constraint_no_empl
    
        # dgdp_total_current = dgdp_total_current + cdgdp_supply_constraint + cdgdp_supply_constraint_no_empl
        
        gdp_history = gdp_base + dgdp_total
        self.V.write_var('gdp_base', year, gdp_history)
        if year == self.model_start:
            self.V.write_var('gdp_base', year-1, gdp_history)
    
        print("--- 3.1 GDP module: %s seconds ---" % round(time.time() - module_time, 1))
        module_time = time.time()
        #endregion
    
        #region 3.2_Final_calculations [rgba(155,89,182,0.15)]
        #region desc [rgba(155,89,182,0.60)]
        # ^w    [3.2] Calculate all variables later printed
        #endregion
    
        # def add_regions(base_table):
        #     change_table = base_table.merge(EXOG_VARS.R[['Region_acronyms','Region_names']].rename(columns={'Region_acronyms':'REG_imp'}), how='left')
        #     return(change_table)
        
        # def add_sectors(base_table, product_col='PROD_COMM'):
        #     change_table = base_table.merge(EXOG_VARS.P[['Lfd_Nr','Sector_names']].rename(columns={'Lfd_Nr':product_col}), how='left')
        #     return(change_table)
        
        # def add_meta(base_table, product_col='PROD_COMM'):
        #     change_table = add_regions(base_table)
        #     change_table = add_sectors(change_table, product_col=product_col)
        #     return(change_table)
    
        # def results_table_from_vars(name_, base_table):
        #     list_ = [x for x in temp_vars.keys() if x.startswith(name_)]
        #     change_table = base_table.copy()
        #     for i in list_:
        #         change_table = pd.concat(
        #             [change_table, pd.DataFrame(temp_vars[i], columns = [i])], axis=1)
        #     return(change_table)
    
        # def reorder_cols(table_, first_dimensions):
        #     table_ = table_[first_dimensions + [x for x in table_.columns if x not in first_dimensions]] # reorder
        #     return(table_)
        
        # def results_table(name_, base_table, product_col='PROD_COMM'):
        #     change_table = results_table_from_vars(name_, base_table)
        #     change_table = add_meta(change_table, product_col=product_col)
        #     return(change_table)
        
    
        # dimension_vars = ['REG_imp','Region_names','PROD_COMM','Sector_names']
    
        # #? OUTPUT change
        # output_change = self.V.read_var("output", year-1, as_df=True).rename(columns={'output':'q_base'})
        # output_change = results_table('dq_', output_change)
        # # add normal output
        # normal_output = DYNAMIC['normal_output'][year-1][['REG_imp','PROD_COMM','normal_output']]
        # output_change = output_change.merge(normal_output)
        # output_change = reorder_cols(output_change, dimension_vars)
    
        # #? EMPLOYMENT changes
        # # TODO
        # empl_change = self.V.read_var('employment_base', year, as_df=True)
        # empl_change = results_table('dempl_', empl_change)
        # empl_change = empl_change.merge(self.V.read_var('wage', year, as_df=True))
        # empl_change = empl_change.merge(DYNAMIC['labour_force'][year], how='left', on='REG_imp')
        # empl_change = reorder_cols(empl_change, dimension_vars)
    
        # #? GDP changes
        # gdp_change = MRIO_vec_to_df_DEF(gdp_base, 'gdp_base')
        # gdp_change = results_table('dgdp_', gdp_change)
        # gdp_change = reorder_cols(gdp_change, dimension_vars)
    
        # #? PRICE changes
        # price_change = MRIO_vec_to_df_DEF(dp_ctax, 'dp_ctax')
        # price_change = results_table_from_vars('dp_', price_change)
        # price_change = results_table_from_vars('v_', price_change)
        # price_change = price_change.merge(DYNAMIC['price_index'][year], how='outer')
        # price_change = price_change.merge(HH_price[['REG_imp','TRAD_COMM','delta_p_avg']].rename(columns={'TRAD_COMM':'PROD_COMM','delta_p_avg':'dp_avg_hh_price'}), how='outer')
        # # price_change = price_change.merge(DYNAMIC['investment_price_index'][year-1].astype({'PROD_COMM':'float'}), how='outer')
        # price_change = add_meta(price_change)
        # price_change = reorder_cols(price_change, dimension_vars)
    
        #region 4_Dynamic_variables [rgba(241,196,15,0.10)]
        #region desc [rgba(241,196,15,0.70)]
        # ! new IO already calculated here, to be able to report intermediates trade
        # ^w    [4.1] Input-output table
        # ^w        take the A matrix after all the deltas and take new output
        # ^w        re-calculate the full matrix, use it as a new MRIO base matrix in the next year
        #endregion
        new_IO = MRIO_mat_to_df(A_iochange, len(EXOG_VARS.P), EXOG_VARS.R).rename(columns={'target-country-iso3':'REG_imp','origin-country-iso3':'REG_exp'})
        new_IO = new_IO.drop(columns=['target-country','origin-country'])
        output = MRIO_vec_to_df_DEF((self.V.read_var("output", year-1) + dq_total), "q_total")
        new_IO = new_IO.merge(output, how='left', on=['REG_imp','PROD_COMM']) #type: ignore
        new_IO['z_bp'] = new_IO['value'] * new_IO['q_total']
        new_IO['a_bp'] = new_IO['value']
        new_IO['a_tech'] = new_IO.groupby(['REG_imp','TRAD_COMM','PROD_COMM'])['a_bp'].transform('sum')            
                
        new_IO = new_IO.rename(columns={'q_total':'output'})
        new_IO = new_IO[['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','z_bp','output','a_bp','a_tech']]
        new_IO = new_IO.set_index(['REG_imp','PROD_COMM','REG_exp','TRAD_COMM'])
        # INDEX: REG_imp PROD_COMM REG_exp TRAD_COMM | VALUES: z_bp output a_bp a_tech
        self.V.write_var_df('new_IO', year, new_IO.reset_index())
        del new_IO
        #endregion
    
        # # Demand change
        # def agg_demand(df_, var_, rename_):
        #     df_ = df_.reset_index()
        #     df_ = df_.groupby(['REG_imp','TRAD_COMM']).agg({var_:'sum'}).reset_index()
        #     df_ = df_.rename(columns={var_:rename_})
        #     return(df_)
        
        # demand_hh_base = agg_demand(EXOG_VARS.HH_BASE, 'VIPA', 'y_hh')
        # demand_fcf_base = agg_demand(EXOG_VARS.FCF_BASE, 'VDFA', 'y_fcf')
        # demand_gov_base = agg_demand(EXOG_VARS.GOV_BASE, 'VIGA', 'y_gov')
    
        # demand_inv_induced = agg_demand(DYNAMIC['inv_induced_L1'], 'dy', 'dy_inv_induced')
        # demand_inv_recyc = agg_demand(INV_model.dy_inv_recyc, 'dy', 'dy_inv_recyc')
        # demand_inv_exog = agg_demand(INV_model.investment_exog, 'dk', 'dy_inv_exog')
    
        # demand_hh_price = agg_demand(HH_price_eff, 'delta_y_price', 'dy_hh_price')
        # demand_hh_inc = agg_demand(HH_inc_eff, 'delta_y_inc', 'dy_hh_inc')
        # demand_hh_tech_substitution = agg_demand(HH_tech_substitution, 'VIPA_imp', 'dy_hh_tech_substitution')
    
        # demand_gov_recyc = agg_demand(GOV_recyc, 'delta_y_gov', 'dy_gov_recyc')
        # demand_gov_delta = agg_demand(DYNAMIC['govt_spending_delta'], 'VIGA', 'dy_gov_delta')
    
        # demand_trade_hh = agg_demand(fd_trade_response['3d']['HH_d'], 'dVIPA', 'dy_trade_hh')
        # demand_trade_fcf = agg_demand(fd_trade_response['3d']['FCF_d'], 'dVDFA', 'dy_trade_fcf')
        # demand_trade_gov = agg_demand(fd_trade_response['3d']['GOV_d'], 'dVIGA', 'dy_trade_gov')
    
        # demand_exog_fd_hh = agg_demand(Scenario.fd_exog.query("PROD_COMM == 'FD_1'"), 'dy', 'dy_fd_exog_hh').astype({'TRAD_COMM':'int'})
        # demand_exog_fd_fcf = agg_demand(Scenario.fd_exog.query("PROD_COMM == 'FD_4'"), 'dy', 'dy_fd_exog_fcf').astype({'TRAD_COMM':'int'})
        # demand_exog_fd_gov = agg_demand(Scenario.fd_exog.query("PROD_COMM == 'FD_3'"), 'dy', 'dy_fd_exog_gov').astype({'TRAD_COMM':'int'})
    
        # demand_calibration_hh = agg_demand(DYNAMIC['residual_consumption_hh'], 'VIPA', 'dy_calibration_hh')
        # demand_calibration_gov = agg_demand(DYNAMIC['residual_consumption_gov'], 'VIGA', 'dy_calibration_gov')
        # demand_calibration_fcf = agg_demand(DYNAMIC['residual_consumption_fcf'], 'VDFA', 'dy_calibration_fcf')
    
        # demand_intermediates = agg_demand(DYNAMIC['new_IO'], 'z_bp', 'dy_intermediates')
    
        # demand_change = demand_hh_base.merge(demand_fcf_base, how='outer', on=['REG_imp','TRAD_COMM']).merge(demand_gov_base, how='outer', on=['REG_imp','TRAD_COMM'])
        # demand_change = demand_change.merge(demand_inv_induced, how='outer').merge(demand_inv_recyc.astype({'TRAD_COMM':'int'}), how='outer').merge(demand_inv_exog, how='outer', on=['REG_imp','TRAD_COMM'])
        # demand_change = demand_change.merge(demand_hh_price, how='outer').merge(demand_hh_inc, how='outer').merge(demand_gov_recyc, how='outer').merge(demand_gov_delta, how='outer')
        # demand_change = demand_change.merge(demand_trade_hh, how='outer').merge(demand_trade_fcf, how='outer').merge(demand_trade_gov, how='outer')
        # demand_change = demand_change.merge(demand_calibration_hh, how='outer').merge(demand_calibration_gov, how='outer').merge(demand_calibration_fcf, how='outer')
        # demand_change = demand_change.merge(demand_hh_tech_substitution, how='outer')
        # demand_change = demand_change.merge(demand_exog_fd_hh, how='outer').merge(demand_exog_fd_fcf, how='outer').merge(demand_exog_fd_gov, how='outer')
        # demand_change = demand_change.merge(demand_intermediates, how='outer')
        # demand_change = add_meta(demand_change, product_col='TRAD_COMM')
        # demand_change = reorder_cols(demand_change, ['REG_imp','Region_names','TRAD_COMM','Sector_names'])
    
        # unmet = IO_model.calc_fd_impact(supply_constraint['dy_supply_constraint'])
    
        # # Investment change
        # #! fd_trade_response does NOT need to be included, because it does not change DEMAND only how demand is supplied!
        # investment_change = self.V.read_var("dk_base", year, as_df=True).merge(self.V.read_var("k", year, as_df=True))
    
        # def agg_inv(df_, rename_):
        #     df_ = df_.groupby(['REG_imp','PROD_COMM']).agg({'dk':'sum'}).reset_index()
        #     df_ = df_.rename(columns={'dk':rename_})
        #     return(df_)
    
        # investment_induced = agg_inv(DYNAMIC['inv_induced_L1'].rename(columns={'dy':'dk'}),'dk_induced')
        # investment_exog = agg_inv(INV_model.investment_exog, 'dk_exog')
        # investment_recyc = agg_inv(INV_model.investment_recyc, 'dk_recyc') # TODO this is NOMINAL
        # investment_change = investment_change.merge(investment_induced, how='outer').merge(investment_exog, how='outer', on=['REG_imp','PROD_COMM'])\
        #     .merge(investment_recyc, how='outer')
    
        # try:
        #     investment_change = add_meta(investment_change.drop(columns=['share']))
        # except KeyError:
        #     investment_change = add_meta(investment_change)
        # investment_change = reorder_cols(investment_change, dimension_vars)
    
        # ## TRADE
        # # REG_imp \ PROD_COMM \ export \ import
        # # need to include intermediates too!
        # def agg_trade(df_, var_, rename_):
        #     df_ = df_.reset_index()
        #     df_['domestic'] = df_.apply(lambda x: 'domestic' if x['REG_imp'] == x['REG_exp'] else 'import', axis=1)
        #     df_import = df_[df_['domestic']=='import'].drop(columns=['domestic']).groupby(['REG_imp','TRAD_COMM']).agg({var_:'sum'}).reset_index()
        #     df_import = df_import.rename(columns={var_:"import_{}".format(rename_)})
        #     df_export = df_[df_['domestic']=='import'].drop(columns=['domestic']).groupby(['REG_exp','TRAD_COMM']).agg({var_:'sum'}).reset_index()
        #     df_export = df_export.rename(columns={var_:"export_{}".format(rename_), 'REG_exp':'REG_imp'})
        #     df_ = df_import.merge(df_export, how="outer")
        #     return(df_)
    
        # def cint(df):
        #     df['TRAD_COMM'] = df['TRAD_COMM'].astype(int)
        #     return(df)
    
        # trade_hh_base = agg_trade(EXOG_VARS.HH_BASE, 'VIPA', 'hh_base')
        # trade_fcf_base = agg_trade(EXOG_VARS.FCF_BASE, 'VDFA', 'fcf_base')
        # trade_gov_base = agg_trade(EXOG_VARS.GOV_BASE, 'VIGA', 'gov_base')
    
        # trade_inv_induced = agg_trade(DYNAMIC['inv_induced_L1'], 'dy', 'inv_induced')
        # trade_inv_recyc = agg_trade(INV_model.dy_inv_recyc, 'dy', 'inv_recyc')
        # trade_inv_exog = agg_trade(INV_model.dy_inv_exog, 'dy', 'inv_exog')
    
        # trade_hh_price = agg_trade(HH_price_eff, 'delta_y_price', 'hh_price')
        # trade_hh_inc = agg_trade(HH_inc_eff, 'delta_y_inc', 'hh_inc')
        # trade_hh_tech_substitution = agg_trade(HH_tech_substitution, 'VIPA_imp','hh_tech')
    
        # trade_gov_recyc = agg_trade(GOV_recyc, 'delta_y_gov', 'gov_recyc')
        # trade_gov_delta = agg_trade(DYNAMIC['govt_spending_delta'], 'VIGA', 'gov_delta')
    
        # trade_trade_hh = agg_trade(fd_trade_response['3d']['HH_d'], 'dVIPA', 'trade_hh')
        # trade_trade_fcf = agg_trade(fd_trade_response['3d']['FCF_d'], 'dVDFA', 'trade_fcf')
        # trade_trade_gov = agg_trade(fd_trade_response['3d']['GOV_d'], 'dVIGA', 'trade_gov')
    
        # # ! need to add intermediates
        # trade_intermediates_base = agg_trade(EXOG_VARS.IND_BASE, 'z_bp', 'intermediates_base')
        # trade_intermediates_new = agg_trade(DYNAMIC['new_IO'], 'z_bp', 'intermediates_new')
    
        # trade_change = trade_hh_base.merge(trade_fcf_base, how='outer', on=['REG_imp','TRAD_COMM']).merge(trade_gov_base, how='outer', on=['REG_imp','TRAD_COMM'])
        # trade_change = trade_change.merge(trade_inv_induced, how='outer').merge(cint(trade_inv_recyc), how='outer').merge(cint(trade_inv_exog), how='outer', on=['REG_imp','TRAD_COMM'])
        # trade_change = trade_change.merge(trade_hh_price, how='outer').merge(trade_hh_inc, how='outer').merge(trade_gov_recyc, how='outer').merge(trade_gov_delta, how='outer')
        # trade_change = trade_change.merge(trade_trade_hh, how='outer').merge(trade_trade_fcf, how='outer').merge(trade_trade_gov, how='outer')
        # trade_change = trade_change.merge(trade_intermediates_base, how='outer').merge(trade_intermediates_new, how='outer')
        # trade_change = trade_change.merge(trade_hh_tech_substitution, how='outer')
        # trade_change = add_meta(trade_change, product_col='TRAD_COMM')
        # trade_change = reorder_cols(trade_change, ['REG_imp','Region_names','TRAD_COMM','Sector_names'])
    
        #  tax_rev_interm = DYNAMIC['emission_cost_intermediates'][year].groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev'})
        #         tax_rev_hh = DYNAMIC['emission_cost_hh'][year].groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev_hh'})
        #         tax_rev_fcf = DYNAMIC['emission_cost_fcf'][year].groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev_fcf'})
        #         tax_rev_gov = DYNAMIC['emission_cost_gov'][year].groupby(['REG_imp']).agg({'emission_cost':'sum'}).reset_index().rename(columns={'emission_cost':'tax_rev_gov'})
    
        ## CARBON revenues
        # carbon_revenue = pd.concat([DYNAMIC['emission_cost_intermediates'][year], DYNAMIC['emission_cost_hh'][year],DYNAMIC['emission_cost_fcf'][year], DYNAMIC['emission_cost_gov'][year]])
    
        # total_revenue = Tax_rev.build_tax_rev_result(tax_rev_prod, tax_rev_hh_base)
        # total_revbase = Tax_rev.build_tax_rev_result(
        #     tax_rev_prod_base.rename(columns = {"tax_rev_prod_base": "tax_rev_prod"}),
        #     tax_rev_hh_base.rename(columns = {"tax_rev_hh_base": "tax_rev_hh"}))
        # total_revbase = total_revbase.rename(columns = {"tax_rev_prod": "tax_rev_prod_base"})
        # total_revenue = total_revenue.merge(total_revbase, how="left", on =["REG_imp", "PROD_COMM"])
    
        #? ENERGY change
        
        # helper = ['FD_1','FD_3','FD_4']
        # energy_change = ener_base.rename(columns={"fuel_use":'energy_flows'}).query("PROD_COMM != @helper")
        # energy_change['PROD_COMM'] = energy_change['PROD_COMM'].astype("int")
        # self.V.write_var('energy_flows', year, energy_change, from_df=True)

        # energy_change = ener_base.rename(columns={"fuel_use":'energy_flows_fd'}).query("PROD_COMM == @helper")
        # energy_change['PROD_COMM'] = energy_change['PROD_COMM'].astype("str")
        # self.V.write_var('energy_flows_fd', year, energy_change.rename(columns={'PROD_COMM':'FD'}), from_df=True)

        # energy_change = MRIO_vec_to_df_DEF(ener_base, 'ener_base')
        # energy_change = results_table('dener_', energy_change)
        # energy_change = reorder_cols(energy_change, dimension_vars)

        energy_change = ener_base
        
    
        if self.ftt_run:
            ## FTT: Power
            ftt_model, DYNAMIC = solve_year_ftt(self, year, ftt_model, DYNAMIC, Scenario,
                                                          ener_base, IO_model, self.model_start, self.model_end)
                
        # for i in range(len(ftt_model.titles['RTI'])):
        #     print(ftt_model.titles['RTI'][i])
        #     pd.DataFrame(ftt_model.output['S0']['MEWG'][i, :, 0, :], index = ftt_model.titles['T2TI'], columns = range(2010, 2051)).T.plot()
    
        ## EMISSIONS
    
        Energy_emissions = ener_balance(EXOG_VARS, Scenario, self.refining_sectors)
        emissions = Energy_emissions.delta_emissions(dq_total, A_iochange, IO_model.A_BASE, self.V.read_var("output", year-1))
        emissions = emissions.astype({'target-sector':'int16'})
        emissions = EXOG_VARS.mrio_list.merge(emissions, how='left', left_on=['Reg_ID','Sec_ID'], right_on=['target-country-iso3','target-sector'])
        emissions = emissions.drop(columns=['target-country-iso3','target-sector']).fillna(0)
        emissions = emissions.groupby(['Reg_ID','Sec_ID']).agg({'deltaPollutant':'sum', 'qPollutant':'sum',
                                                                                            'deltaProcess':'sum', 'qProcess':'sum', 
                                                                                            'deltaPollutant_nostructuralchange':'sum'}).reset_index()
    
        ## GOVT revenues
        # !!! this shouldn't stay here
        if year == self.model_start:
            DYNAMIC['government_spending_by_revenue_source'] = GOV_model.calc_initial_spending()
            DYNAMIC['government_spending_by_revenue_source'].iloc[:,1:] = 'NA'
        # govt_revenues = add_regions(DYNAMIC['government_spending_by_revenue_source'])
    
        labor_comp = Prod_cost.labor_comp.reset_index().rename(columns={'labor':'labor_comp_base'})
        if self.SWITCH_WITHIN_YEAR_LOOP:
            dlabor_sec_ = dlabor_sec.copy()
            dlabor_sec_.columns = ['REG_imp','PROD_COMM','dlabor']
            labor_comp = labor_comp.merge(dlabor_sec_)
    
        if year == self.model_start:
            DYNAMIC['other_country_vars'] = pd.DataFrame({'REG_imp':EXOG_VARS.R_list})\
                .assign(interest_rate = 'NA', interest_rate_real = 'NA', gdp_deflator = 'NA', output_gap = 'NA', cpi = 'NA')
        # other_summary_vars = add_regions(DYNAMIC['other_country_vars'])
        # ! add HH savings rate
        # ? nominal income (compensation) - nominal demand (consumption)
        nom_income = labor_comp.copy()
        nom_income['income'] = nom_income['labor_comp_base'] + nom_income['dlabor']
        nom_income = nom_income.groupby(['REG_imp']).agg({'income':'sum'}).reset_index()
        
        nom_spending = EXOG_VARS.HH_BASE.join(HH_price_eff, how='left').join(HH_inc_eff, how='left').join(HH_tech_substitution.set_index(['REG_imp','REG_exp','TRAD_COMM']), how='left')
        nom_spending = nom_spending.fillna(0)
        nom_spending['VIPA'] = nom_spending['VIPA'] + nom_spending['delta_y_price'] + nom_spending['delta_y_inc'] + nom_spending['VIPA_imp']
        nom_spending = nom_spending[['VIPA']].copy().reset_index().merge(self.V.read_var('price_index', year, as_df=True).rename(columns={'REG_imp':'REG_exp','PROD_COMM':'TRAD_COMM'}), how='left')
        nom_spending['VIPA_nominal'] = nom_spending['VIPA'] * nom_spending['price_index']
        nom_spending = nom_spending.groupby(['REG_imp']).agg({'VIPA_nominal':'sum'}).reset_index()
    
        nom_spending = nom_income[['REG_imp','income']].merge(nom_spending[['REG_imp','VIPA_nominal']], how='outer', on=['REG_imp'])
        nom_spending['hh_savings_rate'] = 1.0 - nom_spending['VIPA_nominal'] / nom_spending['income']
        nom_spending = nom_spending[['REG_imp','hh_savings_rate','income']].copy()
    
        # other_summary_vars = other_summary_vars.merge(nom_spending, how='left', on=['REG_imp'])
    
    
        # VALUE ADDED (current)
        # va_components = DYNAMIC['value_added'][year-1]
        # va_components = add_meta(va_components)
        # va_components = va_components.merge(MRIO_vec_to_df_DEF(gdp_base_current, 'gdp_base_current'), how='left')
        # va_components = va_components.merge(MRIO_vec_to_df_DEF(dgdp_total_current, 'dgdp_total_current'), how='left')
        # va_components = va_components.merge(self.V.read_var('profit_rate', year-1, as_df=True), how='left')
        # va_components = va_components.merge(MRIO_vec_to_df_DEF(profit_rate_mean_L1, 'profit_rate_mean'), how='left')
        # # va_components = va_components.merge(MRIO_vec_to_df_DEF(DYNAMIC['profit_rate_mean'][year-1], 'profit_rate_mean'), how='left')
        # va_components = reorder_cols(va_components, ['REG_imp','Region_names','PROD_COMM','Sector_names'])
    
        #endregion
    
        #region 3.3_Print_results [rgba(155,89,182,0.15)]
        #region desc [rgba(155,89,182,0.60)]
        # ^w    [3.3] Print results
        # ^w        if dynamic, then results are appended to the same file year-by-year
        #endregion

        # Results = results(scenario=self.scenario_name,regions=EXOG_VARS.R)
        # results_dict = {
        #     'output': output_change, # done
        #     'employment': empl_change, # done, add wages
        #     'gdp': gdp_change, # done
        #     'value_added': va_components,
        #     'demand': demand_change, # done
        #     'unmet_demand': unmet,
        #     'price': price_change, # done
        #     'tax_revenue': carbon_revenue, # done
        #     'govt_revenues': govt_revenues, # done, #! first year wrong
        #     'investment': investment_change, # done
        #     'trade': trade_change, # doneF
        #     'emissions': emissions, #! function needs to be updated
        #     'energy': energy_change,
        #     'other_summary': other_summary_vars
        # }
    
        # Results.save_change(results_dict, year=year)
    
        print("--- 3.2 writing results file: %s seconds ---" % round(time.time() - module_time, 1))
    
        #endregion
        #endregion
    
        #region 4_Dynamic_variables [rgba(241,196,15,0.10)]
        #region desc [rgba(241,196,15,0.70)]
        # ^w    [4] DYNAMIC VARIABLES CALCULATION
        #endregion
    
        #region 4.1_Input-output [rgba(241,196,15,0.2)]
        #region desc [rgba(241,196,15,0.70)]
        # ^w    [4.1] Input-output table
        # ^w        take the A matrix after all the deltas and take new output
        # ^w        re-calculate the full matrix, use it as a new MRIO base matrix in the next year
        # ! MOVED TO EARLIER
        #endregion
    
    
        #region desc [rgba(241,196,15,0.70)]
        # ^w    [4.2] New baseline values
        # ^w        take deltas and form new baseline
        #endregion
        
        module_time = time.time()

        # ! again, shouldn't change bc we don't yet have scenario impacts
        # ^b NEW EMPLOYMENT = basically carrying over employment changes to next year
        dyn_empl = MRIO_vec_to_df(self.V.read_var('dempl_total', year),"dempl",len(EXOG_VARS.P), EXOG_VARS.R).rename(columns={'target-country-iso3':'REG_imp','target-sector':'PROD_COMM'})
        dyn_empl = dyn_empl.merge(self.V.read_var("employment_base", year, as_df=True), on=['REG_imp','PROD_COMM'])
        dyn_empl['employment_base'] = dyn_empl['employment_base'] + dyn_empl['dempl']
        self.V.write_var("employment_base", year+1, dyn_empl.drop(columns=['dempl','target-country']), from_df=True)
    
        unemp_rate = Empl_model.calc_unemployment(self.V.read_var("employment_base", year+1, as_df=True), self.V.read_var('labour_force', year, as_df=True).rename(columns={'labour_force':'LF'}))
        self.V.write_var("unemployment_rate", year, unemp_rate, from_df=True)
    
        print("--- 4.2.1 DYNAMICS - employment: %s seconds ---" % round(time.time() - module_time, 1))
        module_time = time.time()
        
        # ^b NEW HH CONSUMPTION
        # index[REG_imp | REG_exp | TRAD_COMM] | VIPA
        dyn_hh_cons = HH_model.dHH_inc.reset_index().merge(HH_model.dHH_price.reset_index()).merge(HH_model.HH.reset_index(), how="outer")
        dyn_hh_cons = dyn_hh_cons.merge(HH_model.dHH_save.reset_index())
        dyn_hh_cons = dyn_hh_cons.merge(self.V.read_var('dy_hh_exog', year, as_df=True))
        dyn_hh_cons = dyn_hh_cons.merge(fd_trade_response['3d']['HH_d'].rename(columns={'dVIPA':'delta_y_trade'}), how='outer')
        dyn_hh_cons = dyn_hh_cons.merge(HH_tech_substitution.rename(columns={'VIPA_imp':'delta_y_tech'}), how='outer')
    
        # add growth
        # if year > self.model_start:
        dyn_hh_cons = dyn_hh_cons.merge(DYNAMIC['residual_consumption_hh'].reset_index().rename(columns={'VIPA':'delta_y_growth'}), how='outer')
        # dyn_hh_cons = dyn_hh_cons.merge(dy_hh_empl_LSC, how='outer', on=['REG_imp','REG_exp','TRAD_COMM'])
        dyn_hh_cons.fillna(0, inplace=True)
        dyn_hh_cons['VIPA'] = dyn_hh_cons['VIPA'] + dyn_hh_cons['delta_y_inc'] + dyn_hh_cons['delta_y_price'] + dyn_hh_cons['delta_y_save'] \
              + dyn_hh_cons['delta_y_growth']\
              + dyn_hh_cons['delta_y_trade'] + dyn_hh_cons['delta_y_tech'] + dyn_hh_cons['dy_hh_exog']
        # + dyn_hh_cons['dy_LSC']
        # 'dy_LSC'
        try:
            dyn_hh_cons = dyn_hh_cons.drop(columns=['index'])
        except KeyError:
            pass
    
        dyn_hh_cons = dyn_hh_cons.drop(columns=['delta_y_inc','delta_y_price','delta_y_save','delta_y_growth','delta_y_trade','delta_y_tech','dy_hh_exog'])\
            .set_index(['REG_imp','REG_exp','TRAD_COMM'])
        # else:
            # dyn_hh_cons['VIPA'] = dyn_hh_cons['VIPA'] + dyn_hh_cons['delta_y_inc'] + dyn_hh_cons['delta_y_price']
            # dyn_hh_cons = dyn_hh_cons.drop(columns=['delta_y_inc','delta_y_price']).set_index(['REG_imp','REG_exp','TRAD_COMM'])
        
        # ! NO NEGATIVE VALUES
        dyn_hh_cons['VIPA'] = dyn_hh_cons['VIPA'].apply(lambda x: x if x > 0.0 else 0.0) 
        self.V.write_var('household_consumption', year, dyn_hh_cons.reset_index().rename(columns={'VIPA':'household_consumption'}), from_df=True)
    
        print("--- 4.2.2 DYNAMICS - consumption: %s seconds ---" % round(time.time() - module_time, 1))
        module_time = time.time()
    
        # ^b NEW FCF CONSUMPTION
        # index[REG_imp | REG_exp | TRAD_COMM] | VDFA
        # need to add base + recycling (?) + exog (?) + induced [from DYNAMIC]
        dyn_fcf_cons = INV_model.FCF.reset_index().astype({'TRAD_COMM':'int16'})\
        .merge(DYNAMIC['residual_consumption_fcf'].reset_index().rename(columns={'VDFA':'dy_residual'}), how='outer')\
            .merge(INV_model.dy_inv_recyc.astype({'TRAD_COMM':'int16'}).rename(columns={'dy':'dy_recyc'}), how='outer')\
                .merge(INV_model.dy_inv_exog.astype({'TRAD_COMM':'int16'}).rename(columns={'dy':'dy_exog'}), how='outer')
                # .merge(dy_fcf_empl_LSC, how='outer')
        if year > self.model_start:
            dyn_fcf_cons = dyn_fcf_cons.merge(DYNAMIC['inv_induced_L1'].groupby(['REG_imp','REG_exp','TRAD_COMM']).agg({'dy':'sum'}).reset_index()\
                                              .rename(columns={'dy':'dy_induced'}), how='outer')
        else:
            dyn_fcf_cons['dy_induced'] = 0
        dyn_fcf_cons = dyn_fcf_cons.merge(fd_trade_response['3d']['FCF_d'].rename(columns={"dVDFA":'dy_trade'}))
    
        dyn_fcf_cons = dyn_fcf_cons.fillna(0)    
        # dyn_fcf_cons['VDFA'] = dyn_fcf_cons['VDFA'] + dyn_fcf_cons['dy_recyc'] + dyn_fcf_cons['dy_exog'] + dyn_fcf_cons['dy_induced']\
        #? exclude dy_exog
        dyn_fcf_cons['VDFA'] = dyn_fcf_cons['VDFA'] + dyn_fcf_cons['dy_recyc'] + dyn_fcf_cons['dy_induced']\
            + dyn_fcf_cons['dy_trade'] + dyn_fcf_cons['dy_residual']
        # + dyn_fcf_cons['dy_LSC']
        # 'dy_LSC'
        dyn_fcf_cons = dyn_fcf_cons.drop(columns=['dy_recyc','dy_exog','dy_induced','dy_trade','dy_residual']).set_index(['REG_imp','REG_exp','TRAD_COMM'])
        try:
            dyn_fcf_cons = dyn_fcf_cons.drop(columns=['index'])
        except KeyError:
            pass
    
        # ! NO NEGATIVE VALUES
        dyn_fcf_cons['VDFA'] = dyn_fcf_cons['VDFA'].apply(lambda x: x if x > 0.0 else 0.0) 
        self.V.write_var('fcf_consumption', year, dyn_fcf_cons.reset_index().rename(columns={'VDFA':'fcf_consumption'}), from_df=True)
    
        print("--- 4.2.3 DYNAMICS - FCF: %s seconds ---" % round(time.time() - module_time, 1))
        module_time = time.time()
    
        # ^b CALC CPI
        hh_cons = dyn_hh_cons.copy()
        hh_cons['shares'] = hh_cons['VIPA'] / hh_cons.groupby(['REG_imp'])['VIPA'].transform('sum')
        cpi_shares = MRIO_vec_to_df_DEF(dp_trade, 'd_price').rename(columns={'REG_imp':'REG_exp','PROD_COMM':"TRAD_COMM"})
        cpi_shares = hh_cons.reset_index().merge(cpi_shares, how='left', on=['TRAD_COMM','REG_exp'])
        cpi_shares['cpi'] = cpi_shares['d_price'] * cpi_shares['shares']
        cpi_shares = cpi_shares.groupby(['REG_imp']).agg({'cpi':'sum'}).reset_index()
        cpi_shares['cpi'] = cpi_shares['cpi'] + 1
        cpi_shares = cpi_shares.merge(self.V.read_var('cpi', year-1, as_df=True).rename(columns={'cpi':'cpi_prev'}), how='left', on='REG_imp')
        cpi_shares['cpi'] = cpi_shares['cpi'] * cpi_shares['cpi_prev']
        self.V.write_var('cpi', year, cpi_shares.drop(columns=['cpi_prev']), from_df=True)
    
        # ^b LABOR COMP
        # index[REG_imp | REG_exp | TRAD_COMM] | labor
        dyn_labor_comp = labor_comp
        if self.SWITCH_WITHIN_YEAR_LOOP:
            dyn_labor_comp['labor'] = dyn_labor_comp['labor_comp_base'] + dyn_labor_comp['dlabor']
            dyn_labor_comp = dyn_labor_comp.drop(columns=['dlabor','labor_comp_base']).set_index(['REG_imp','PROD_COMM'])
        else:
            dyn_labor_comp = dyn_labor_comp.rename(columns={'labor_comp_base':'labor'}).set_index(['REG_imp','PROD_COMM'])
        DYNAMIC['new_labor_comp'] = dyn_labor_comp
    
        # ^b NEW q_base (output)
        output_pre = self.V.read_var("output", year-1)
        dyn_qbase = output_pre + dq_total
        if len(dyn_qbase[dyn_qbase < 0]) > 0:
            # TODO temp
            dyn_qbase[dyn_qbase < 0] = 0.0
            dead_mask = (dyn_qbase == 0.0)
            empl = self.V.read_var("employment_base", year+1)
            empl[dead_mask] = 0.0
            self.V.write_var("employment_base", year+1, empl)
            # Freeze price at last year's level rather than zeroing:
            # setting price_index=0 makes goods appear free, causing NaN/inf in trade
            # computations (division by zero in calc_IO_coef) and "free goods" distortions.
            price_frozen = self.V.read_var('price_index', year-1)
            curr_price = self.V.read_var('price_index', year)
            curr_price[dead_mask] = price_frozen[dead_mask]
            self.V.write_var('price_index', year, curr_price)
            # Zero dp_all for dead sectors: dp_all was computed before zeroing and can be
            # very large (ctax pushes v_ctax to its 3.0 cap as output→0). If not zeroed,
            # delta_price_yoy carries this into the next year's energy elasticity model,
            # triggering explosive cross-price substitution to substitute sectors.
            dp = self.V.read_var('dp_all', year)
            dp[dead_mask] = 0.0
            self.V.write_var('dp_all', year, dp)
            # delta_price_yoy was already written before this block (from the original
            # large dp_all). Correct it now so the next year's energy elasticity model
            # does not trigger explosive cross-price substitution to substitute sectors.
            dyoy = self.V.read_var('delta_price_yoy', year)
            dyoy[dead_mask] = 0.0
            self.V.write_var('delta_price_yoy', year, dyoy)
            # Zero final demand for dead sectors so the Leontief system does not
            # generate demand that would force output < 0 again in subsequent years.
            # Dead producer (REG_imp=R, PROD_COMM=P) ≡ dead supply (REG_exp=R, TRAD_COMM=P).
            _out_df = self.V.read_var("output", year-1, as_df=True)
            _dead_supply = _out_df.loc[dead_mask, ['REG_imp','PROD_COMM']].rename(
                columns={'REG_imp': 'REG_exp', 'PROD_COMM': 'TRAD_COMM'}).assign(_dead=True)
            if len(_dead_supply) > 0:
                for _var, _col in [('household_consumption', 'household_consumption'),
                                   ('fcf_consumption',        'fcf_consumption')]:
                    _df = self.V.read_var(_var, year, as_df=True)
                    _flag = _df[['REG_exp','TRAD_COMM']].merge(
                        _dead_supply, how='left', on=['REG_exp','TRAD_COMM'])['_dead'].fillna(False)
                    _df.loc[_flag.values, _col] = 0.0
                    self.V.write_var(_var, year, _df, from_df=True)
                # Zero IO flows in new_IO (A-matrix base) for dead sectors.
                # Buyer side: dead sector demands no intermediate inputs.
                # Seller side: dead sector supplies nothing to other sectors.
                _dead_buyers = _dead_supply[['REG_exp','TRAD_COMM']].rename(
                    columns={'REG_exp': 'REG_imp', 'TRAD_COMM': 'PROD_COMM'}).assign(_dead_buy=True)
                _new_IO = self.V.read_var_df('new_IO', year).copy()
                _new_IO = _new_IO.merge(_dead_buyers, how='left', on=['REG_imp','PROD_COMM'])
                _new_IO = _new_IO.merge(
                    _dead_supply[['REG_exp','TRAD_COMM']].assign(_dead_sell=True),
                    how='left', on=['REG_exp','TRAD_COMM'])
                _new_IO.loc[_new_IO['_dead_buy'].fillna(False), ['z_bp','a_bp','a_tech']] = 0.0
                _new_IO.loc[_new_IO['_dead_sell'].fillna(False), ['z_bp','a_bp']] = 0.0
                _new_IO = _new_IO.drop(columns=['_dead_buy','_dead_sell'])
                # Recompute a_tech after seller-side zeroing may have changed grouped sums
                _new_IO['a_tech'] = _new_IO.groupby(['REG_imp','TRAD_COMM','PROD_COMM'])['a_bp'].transform('sum')
                self.V.write_var_df('new_IO', year, _new_IO)

        self.V.write_var('output', year, dyn_qbase)
    
        # ^b CALC PRODUCTIVITY
        prod = np.nan_to_num(dyn_qbase / self.V.read_var("employment_base", year+1))
        self.V.write_var('productivity', year, prod)

        print("--- 4.2.4 DYNAMICS - Others: %s seconds ---" % round(time.time() - module_time, 1))
        module_time = time.time()
    
        va_current = gdp_base_current + dgdp_total_current
        comp_current = (self.V.read_var("wage", year)) * (self.V.read_var("employment_base", year+1)) 
        # + MRIO_df_to_vec_DEF(dlabor_sec.rename(columns=lambda x: re.sub("_[0-9]{1,}", "", x)),"dlabor")
    
        # set tax rates
        if year == self.model_start:
            tax_rates = MRIO_df_to_vec_DEF(DYNAMIC['value_added'][year-1], "taxes") / self.V.read_var("output_current", year-1)
            tax_rates = np.nan_to_num(tax_rates, nan=0.0, posinf=0.0, neginf=0.0)
            for y in self.years:
                self.V.write_var('tax_rates', y, tax_rates)
    
        # set depreciation rate
        if year == self.model_start:
            depr_3 = MRIO_df_to_vec_DEF(DYNAMIC['value_added'][year-3], "depreciation") / \
                self.V.read_var('k', year-3)
            depr_2 = MRIO_df_to_vec_DEF(DYNAMIC['value_added'][year-2], "depreciation") / \
                self.V.read_var('k', year-2)
            depr_1 = MRIO_df_to_vec_DEF(DYNAMIC['value_added'][year-1], "depreciation") / \
                self.V.read_var('k', year-1)
            depr_rate = (depr_3 + depr_2 + depr_1) / 3
            depr_rate = np.nan_to_num(depr_rate)
            depr_rate[depr_rate > 0.06] = 0.06
            depr_rate[depr_rate < 0.001] = 0.001
            for y in self.years:
                self.V.write_var('depreciation_rate', y, depr_rate)
        
        tax_current = self.V.read_var("output", year) * self.V.read_var('price_index', year)\
            * self.V.read_var('tax_rates', year) + MRIO_df_to_vec_DEF(self.V.read_var_df('emission_cost_intermediates', year), 'emission_cost')\
            + MRIO_df_to_vec_DEF(self.V.read_var_df('cbam_cost_intermediates', year), 'cbam_cost') # type: ignore
        
        # ! calculate investment price index
        # inv_conv = pd.melt(EXOG_VARS.INV_CONV, id_vars=['TRAD_COMM'], var_name='PROD_COMM')
        # fcf = DYNAMIC['fcf_consumption'][year].reset_index()
        # fcf['share'] = fcf['VDFA'] / fcf.groupby(['REG_imp','TRAD_COMM'])['VDFA'].transform('sum')
        # fcf = fcf[['REG_imp','REG_exp','TRAD_COMM','share']].copy()
    
        # inv_conv = inv_conv.merge(fcf, how='left')
        # inv_conv['share'] = inv_conv['value'] * inv_conv['share']
        # inv_conv.drop(columns=['value'], inplace=True)
    
        # # PROD_COMM invests in TRAD_COMM
        # inv_conv = inv_conv.merge(DYNAMIC['price_index'][year].rename(columns={'PROD_COMM':'TRAD_COMM','REG_imp':'REG_exp'}))
        # inv_conv['investment_price_index'] = inv_conv['share'] * inv_conv['price_index']
        # inv_conv = inv_conv.groupby(['REG_imp','PROD_COMM']).agg({'investment_price_index':'sum'}).reset_index()
        # inv_price_index = MRIO_df_to_vec_DEF(inv_conv, 'investment_price_index')
    
        if year == self.model_start:
            inv_price_index = self.V.read_var('investment_price_index', year-1, as_df=True)
        else:
            inv_price_index = self.V.read_var('investment_price_index', year-1, as_df=True).merge(DYNAMIC['other_country_vars'][['REG_imp','gdp_deflator']])
            inv_price_index['investment_price_index'] = inv_price_index['investment_price_index'] * (1 + inv_price_index['gdp_deflator'])
        self.V.write_var('investment_price_index', year, inv_price_index[['REG_imp','PROD_COMM','investment_price_index']], from_df=True)

        depr_current = self.V.read_var('k', year) * self.V.read_var('depreciation_rate', year)
        depr_current = depr_current * self.V.read_var('investment_price_index', year)

        profit_current = va_current - comp_current - tax_current - depr_current
        profit_rate_current = profit_current / (self.V.read_var("output", year) * self.V.read_var('price_index', year))
        profit_rate_current = np.nan_to_num(profit_rate_current, nan=0.0, posinf=0.0, neginf=0.0)

        self.V.write_var('profit_rate', year, profit_rate_current)
        self.V.write_var('profit_rate_mean', year, (self.V.read_var('profit_rate_mean', year-1) * 2 + self.V.read_var('profit_rate', year-1)) / 3)
    
        # lag
        # compile data frame
        # VA is nominal!!!! 
        DYNAMIC['value_added'][year] = MRIO_vec_to_df_DEF(comp_current, "compensation").merge(MRIO_vec_to_df_DEF(tax_current, "taxes"))\
            .merge(MRIO_vec_to_df_DEF(profit_current, "profit")).merge(MRIO_vec_to_df_DEF(depr_current, 'depreciation'))
    
        print("--- 4.2.5 DYNAMICS - Value added: %s seconds ---" % round(time.time() - module_time, 1))
        module_time = time.time()

        #? calc save rate; consumption divided by / (compensation / CPI) 
        comp = MRIO_vec_to_df_DEF(comp_current, "compensation").groupby(['REG_imp']).agg({'compensation':'sum'}).reset_index()
        comp = comp.merge(self.V.read_var('cpi', year, as_df=True), how='left', on='REG_imp')
        hh = self.V.read_var('household_consumption', year, as_df=True).groupby(['REG_imp']).agg({'household_consumption':'sum'}).reset_index().rename(columns={'household_consumption':'VIPA'})
        comp = comp.merge(hh, how='left', on='REG_imp')
        comp['save_rate'] = 1 - (comp['VIPA'] / (comp['compensation']/comp['cpi']))

        # ! keep static for now
        # self.V.write_var("save_rate", year, comp[['REG_imp','save_rate']], from_df=True)
        self.V.write_var("save_rate", year, self.V.read_var("save_rate", year-1))
    
        #endregion
    
        #region 4.3_Productivity_labour_comp [rgba(241,196,15,0.15)]
        #region desc [rgba(241,196,15,0.70)]
        # ^w    [4.3] Productivity and labour compensation change
        # ^w        this is pretty much WIP
        # ^w        a change in labour compensation changes consumption AND prices!
        # ^w        if adjust_empl_multiplier is used, then it changes employment too
        # ^w        we want it to be WAGE, not LABOUR COMP change, therefore, adjust with employment change
        # ^w
        # TODO  a lot?
        #endregion
    
        # ! need to re-calculate employment coefficients considering dempl (average employment multipliers change)
        # ! due to q->empl not linear
        # ! this needs to be done before productivity adjustment
    
        #endregion
    
        #region 4.4_Population [rgba(241,196,15,0.15)]
        #region desc [rgba(241,196,15,0.70)]
        # ^w    [4.4] Population based consumption growth
        # ^w        this is pretty much WIP
        # ^w        consumption to grow with UN POP projections, not much else
        # ^w
        #endregion
    
        # get population growth projection
        pop = EXOG_VARS.POPULATION.pipe(lambda d: d[(d['year'] == year) | (d['year'] == year+1)]).copy()
        pop.loc[:,'growth'] = pop['value'] / pop.groupby(['Agg_region'])['value'].shift()
        pop = pop[pop['year'] == year+1]
        # Lfd_Nr_agg | Agg_region | year | value | growth
    
        #region 4.5_Capital_stock [rgba(241,196,15,0.15)]
        #region desc [rgba(241,196,15,0.70)]
        # ^w    [4.5] Capital stock calculations
        # ^w        this is pretty much WIP
        # ^w
        #endregion
    
        #####################
        # INVESTMENT
        #####################
    
        # get this year's investment
        # this is initial in the first year
        # REG_imp | TRAD_COMM | PROD_COMM | VDFA
    
        # ? so the investment in T+1 will be dependent on
        # ? lagged GDP, i.e., GDP in this year (we're still in T+0) compared to GDP T-1
        # ? lagged interest rate change; lagged utilisation change
    
        DYNAMIC['investment_converter'] = INV_CONV.copy()
    
        # load dynamics
        INV_model.load_dynamic({
            'normal_output': self.V.read_var('normal_output', year-1, as_df=True),
            'normal_output_prev1': self.V.read_var('normal_output', year-2, as_df=True),
            'q_base': self.V.read_var("output", year, as_df=True).rename(columns={'output':'q_base'}),
            'q_base_prev1': self.V.read_var("output", year-1, as_df=True).rename(columns={'output':'q_base_prev1'}),
            'gdp': MRIO_vec_to_df_DEF(gdp_base + dgdp_total, 'gdp'),
            'gdp_real_prev': self.V.read_var('gdp_base', year-1, as_df=True).rename(columns={'gdp_base':'gdp'}),
            'gdp_real': self.V.read_var('gdp_base', year, as_df=True).rename(columns={'gdp_base':'gdp'}),
            'dp_prev1': MRIO_vec_to_df_DEF(self.V.read_var('delta_price_yoy', year), 'dp'),
            'dp_prev2': MRIO_vec_to_df_DEF(self.V.read_var('delta_price_yoy', year-1), 'dp'),
            'price_index': self.V.read_var('price_index', year, as_df=True),
            'dk_base': self.V.read_var('dk_base',year, as_df=True),
            'va_prev1': DYNAMIC['value_added'][year], 
            'va_prev2': DYNAMIC['value_added'][year-1],
            'initial_rates': EXOG_VARS.NOMINAL_RATES,
            'interest_rate_adjust': DYNAMIC['interest_rate_adjust']
        })
        if year == self.model_start:
            DYNAMIC['interest_rate_adjust'] = INV_model.calc_dy_inv_induced(True)
        else:
            INV_model.calc_dy_inv_induced(False)
    
        DYNAMIC['other_country_vars'] = INV_model.other_country_summary_vars.merge(self.V.read_var('cpi', year, as_df=True), how='outer', on=['REG_imp'])
    
        # ^ INDUCED INVESTMENT
        # ^ induced investment is lagged one year, i.e. only appears in the year following it's being induced
        # Final demand from investment for capital good in next year
        if self.ftt_run:
            if year > 2025:
                # Add FTT investment final demand here, but first regionally distribute investment
                # Use the distribution from INV_model.investment_induced in the electricity sector to share 
                # capital goods across REG_exp
                elec_investment_induced = INV_model.investment_induced.loc[INV_model.investment_induced.PROD_COMM == 93, :].copy()
                elec_investment_totals = elec_investment_induced.groupby(['REG_imp', 'PROD_COMM']).sum()
                # Merge back the group totals into the original DataFrame
                elec_investment_induced = elec_investment_induced.merge(elec_investment_totals.reset_index()[['REG_imp', 'dy']], on='REG_imp', suffixes=('', '_Total'))
                # Calculate the share (percentage) of each value within its group
                elec_investment_induced['dy_share'] = (elec_investment_induced['dy'] / elec_investment_induced['dy_Total'])
                # Get FTT investment
                ftt_inv0 = pd.DataFrame(ftt_model.investment[year - 1], index = INV_model.R_list, columns = INV_model.P_list).reset_index().melt(
                                            id_vars='index',
                                            var_name='TRAD_COMM',
                                            value_name='FTT_investment'
                                        ).rename(columns={'index': 'REG_imp'})
                ftt_inv1 = pd.DataFrame(ftt_model.investment[year], index = INV_model.R_list, columns = INV_model.P_list).reset_index().melt(
                                            id_vars='index',
                                            var_name='TRAD_COMM',
                                            value_name='FTT_investment'
                                        ).rename(columns={'index': 'REG_imp'})
                
                ftt_inv_chng = ftt_inv1.copy()
                ftt_inv_chng['FTT_investment'] = np.divide(ftt_inv_chng['FTT_investment'], ftt_inv0['FTT_investment'], 
                                                           where = ftt_inv0['FTT_investment'] != 0, 
                                                           out=np.ones_like(ftt_inv_chng['FTT_investment'], 
                                                                            dtype = float))

                                                           # ftt_investment_chng = np.divide(ftt_model.investment[year], ftt_model.investment[year - 1], out=np.zeros_like(ftt_model.investment[year]), 
                #                                       where=ftt_model.investment[year - 1]!=0)
                # ftt_inv_chng = pd.DataFrame(investment_chng, index = INV_model.R_list, columns = INV_model.P_list).reset_index().melt(
                #                             id_vars='index',
                #                             var_name='TRAD_COMM',
                #                             value_name='FTT_investment'
                #                         ).rename(columns={'index': 'REG_imp'})
                elec_investment_induced = elec_investment_induced.merge(ftt_inv1, on=['REG_imp', 'TRAD_COMM'], suffixes=('', '_share'))
                elec_investment_induced = elec_investment_induced.groupby(['REG_exp', 'TRAD_COMM', 'REG_imp']).sum().reset_index()
                # Allcoate matching indices
                elec_investment_induced = elec_investment_induced.merge(INV_model.dy_inv_induced.reset_index(), on=['REG_exp', 'TRAD_COMM', 'REG_imp'], suffixes=('', '_'))
                elec_investment_induced = elec_investment_induced.set_index('index')
                # Add electricity induced investment
                INV_model.dy_inv_induced.loc[elec_investment_induced.index, 'dy'] += elec_investment_induced['FTT_investment']
        
        DYNAMIC["dy_inv_induced_L1"] = MRIO_df_to_vec_DEF(INV_model.dy_inv_induced.rename(columns={'TRAD_COMM':'PROD_COMM','REG_imp':'IMP','REG_exp':'REG_imp'}), 'dy')
        DYNAMIC['inv_induced_L1'] = INV_model.investment_induced
        
        # update the investment vector
        # + baseline investment - DYNAMIC['investment_vector']
        # + induced (calculated above)
        # + exog 
        # + recycled
        investment = self.V.read_var('dk_base', year, as_df=True)\
            .merge(INV_model.investment_induced.groupby(['REG_imp','PROD_COMM']).agg({'dy':'sum'}).reset_index()\
                   .rename(columns={'dy':'dk_induced'}), how='left', on=['PROD_COMM','REG_imp'])\
            .merge(INV_model.investment_exog.groupby(['REG_imp','PROD_COMM']).agg({'dk':'sum'}).reset_index()\
                   .rename(columns={'dk':'dk_exog'}),how='left', on=['PROD_COMM','REG_imp'])\
                .merge(INV_model.investment_recyc.groupby(['REG_imp','PROD_COMM']).agg({'dk':'sum'}).reset_index()\
                       .rename(columns={'dk':'dk_recyc'}),how='left', on=['PROD_COMM','REG_imp']) # TODO this is nominal
        investment = investment.fillna(0)
        # investment['dk'] = investment['dk_induced'] + investment['dk_exog'] + investment['dk_recyc'] + investment['dk_base'] # NOT USED
        investment['dk_base_new'] = investment['dk_induced'] + investment['dk_base'] + investment['dk_recyc']
        # investment in the period that we need to add to capital stock
        if self.ftt_run:
            # if (ftt_model.investment[year - 1].sum() > 0):
            if year > 2025:
                # Set electricity sector investment to 0, final demand of elec investment is added to induced investment
                electr_investment = investment.loc[investment.PROD_COMM == 93, 'dk_base_new'].copy()
                investment.loc[investment.PROD_COMM == 93, 'dk_base_new'] = 0
    
        inv = investment[['REG_imp','PROD_COMM','dk_base_new']].rename(columns={'dk_base_new':'dk_base'})
        self.V.write_var('dk_base', year+1, inv, from_df=True)
    
        print("--- 4.2.6 DYNAMICS - Investment: %s seconds ---" % round(time.time() - module_time, 1))
        module_time = time.time()
    
        #####################
        # CAPITAL STOCK
        #####################
    
        # all capital
        # so capital stock for next year, will be investment this year, on top of capital stock this year
        capital_stock = self.V.read_var('k', year, as_df=True).merge(self.V.read_var('dk_base', year, as_df=True).rename(columns={'dk_base':'dk'})\
                                                             .groupby(['REG_imp','PROD_COMM']).agg({'dk':'sum'}).reset_index())
        
        # ! replace with GLORIA based rates
        capital_stock = capital_stock.merge(self.V.read_var('depreciation_rate', year, as_df=True), how='left', on=['REG_imp','PROD_COMM'])
    
        capital_stock['k'] = capital_stock['k'] * (1-capital_stock['depreciation_rate']) + capital_stock['dk']
        capital_stock['k'] = capital_stock['k'].apply(lambda x: 0 if x < 0 else x)
        cap_stock_next = capital_stock.drop(columns=['dk','depreciation_rate'])
        self.V.write_var('k', year+1, cap_stock_next, from_df=True)
    
        #####################
        # NORMAL OUTPUT
        #####################
    
        # output_average = (DYNAMIC['output'][year-2] + DYNAMIC['output'][year-1] + DYNAMIC['output'][year]) / 3
        # output_avg_prev = (DYNAMIC['output'][year-3] + DYNAMIC['output'][year-2] + DYNAMIC['output'][year-1]) / 3
    
        # ! USE estimated parameters
        # normal_output = DYNAMIC['normal_output']
    
        normal_output_module = normal_output_mod(EXOG_VARS)
        normal_output_module.load_dynamic({
                    'k': self.V.read_var('k', year), # this is capital stock at the END of this year AND the beginning of the next
                    'k1': self.V.read_var('k', year-1),
                    'k2': self.V.read_var('k', year-2),
                    'k3': self.V.read_var('k', year-3),
                    'q1': self.V.read_var("output", year-1),
                    'q2': self.V.read_var("output", year-2),
                    'q3': self.V.read_var("output", year-3),
                    'normal_output_growth_helper': self.V.read_var('normal_output_growth_helper', year-1)
                })
        normal_output_res = normal_output_module.calc_normal_output_dynamic()
        self.V.write_var('normal_output', year, normal_output_res['normal_output'])
        self.V.write_var('normal_output_growth_helper', year, normal_output_res['normal_output_helper'])
    
        # DYNAMIC['normal_output'][year] = MRIO_vec_to_df_DEF(DYNAMIC['output'][year] * 1.1, "normal_output")
    
        if year > self.model_start:
        # ! CALC GOV?
            new_gov_base = EXOG_VARS.GOV_BASE.reset_index().merge(DYNAMIC['govt_spending_delta'].reset_index().rename(columns={'VIGA':'VIGA_dyn'}), how='outer')
            new_gov_base = new_gov_base.merge(fd_trade_response['3d']['GOV_d'].rename(columns={'dVIGA':'VIGA_trade'}), how='outer')
            new_gov_base = new_gov_base.merge(GOV_recyc.reset_index().rename(columns={'delta_y_gov':'VIGA_recyc'}), how="outer", on=['REG_imp','REG_exp','TRAD_COMM'])
            new_gov_base = new_gov_base.merge(DYNAMIC['residual_consumption_gov'].reset_index().rename(columns={'VIGA':'VIGA_residual'}), how='outer')
            # new_gov_base = new_gov_base.merge(dy_gov_empl_LSC, how='outer')
            new_gov_base = new_gov_base.fillna(0)
    
            # ? so at this point; new gov base will include initial state + trade + residual + recycling
            # ? note this all already had effects in the current year
    
            new_gov_base_ = new_gov_base.copy()
            new_gov_base['VIGA'] = new_gov_base['VIGA'] + new_gov_base['VIGA_dyn'] + new_gov_base['VIGA_trade'] + new_gov_base['VIGA_residual'] + new_gov_base['VIGA_recyc']
            #  + new_gov_base['dy_LSC']
            try:
                new_gov_base = new_gov_base.drop(columns=['index'])
            except KeyError:
                pass
    
            # ! NO NEGATIVE VALUES
            new_gov_base['VIGA'] = new_gov_base['VIGA'].apply(lambda x: x if x > 0.0 else 0.0) 
            self.V.write_var('government_consumption', year, new_gov_base.drop(columns=['VIGA_dyn','VIGA_trade','VIGA_residual','VIGA_recyc']).rename(columns={'VIGA':'government_consumption'}), from_df=True)
                                                                                                                                            #  ,'dy_LSC'])
        else:
            self.V.write_var('government_consumption', year, EXOG_VARS.GOV_BASE.reset_index().rename(columns={'VIGA':'government_consumption'}), from_df=True)

        # Zero government_consumption for dead sectors (written after the main zeroing block,
        # so handled here rather than in that block).
        _out_dead = self.V.read_var("output", year, as_df=True)
        _dead_gov = _out_dead.loc[_out_dead['output'] == 0.0, ['REG_imp','PROD_COMM']].rename(
            columns={'REG_imp': 'REG_exp', 'PROD_COMM': 'TRAD_COMM'}).assign(_dead=True)
        if len(_dead_gov) > 0:
            _df = self.V.read_var('government_consumption', year, as_df=True)
            _flag = _df[['REG_exp','TRAD_COMM']].merge(
                _dead_gov, how='left', on=['REG_exp','TRAD_COMM'])['_dead'].fillna(False)
            _df.loc[_flag.values, 'government_consumption'] = 0.0
            self.V.write_var('government_consumption', year, _df, from_df=True)
    
        if year == self.model_start:
            DYNAMIC['government_spending_by_revenue_source'] = GOV_model.calc_initial_spending()
        else:
            DYNAMIC['government_spending_by_revenue_source'] = GOV_model.calc_endog_spending_change(
                    DYNAMIC['government_spending_by_revenue_source'],
                    DYNAMIC['value_added'][year-1], DYNAMIC['value_added'][year],
                    self.V.read_var('gdp_base', year-1, as_df=True).rename(columns={'gdp_base':'gdp'}), self.V.read_var('gdp_base', year, as_df=True).rename(columns={'gdp_base':'gdp'}),
                    self.V.read_var('household_consumption', year-1, as_df=True).rename(columns={'household_consumption':'VIPA'}).set_index(['REG_imp','REG_exp','TRAD_COMM']),
                    self.V.read_var('household_consumption', year, as_df=True).rename(columns={'household_consumption':'VIPA'}).set_index(['REG_imp','REG_exp','TRAD_COMM']),
                    self.V.read_var("wage", year-1), self.V.read_var("wage", year),
                    self.V.read_var("employment_base", year), self.V.read_var("employment_base", year+1),
                    self.V.read_var("output", year-1), self.V.read_var("output", year),
                    MRIO_vec_to_df_DEF(self.V.read_var('delta_price_yoy', year), 'dp'), year
                    )
        government_spending = DYNAMIC['government_spending_by_revenue_source']
        government_spending = government_spending.set_index('REG_imp', inplace=False).sum(axis=1).reset_index()
        government_spending.columns = ['REG_imp','government_spending']
    
        # ? this calculates spending change (compared to initial) for the next year
        # ? self.GOV is the old consumption; but that excludes additions during the year
         
        if year == self.model_start:
            DYNAMIC['govt_spending_delta'] = GOV_model.calc_gov_demand(government_spending, self.V.read_var('price_index', year, as_df=True), self.V.read_var_df('emission_cost_gov', year))
        else:
            DYNAMIC['govt_spending_delta'] = GOV_model.calc_gov_demand(government_spending, self.V.read_var('price_index', year, as_df=True), self.V.read_var_df('emission_cost_gov', year), new_gov_base=new_gov_base_)
    
        print("--- 4.2.7 DYNAMICS - Govt: %s seconds ---" % round(time.time() - module_time, 1))
    
        # Add FTT investment to investment variable and its lag here
        if self.ftt_run:
            # if ftt_model.investment[year - 1].sum() > 0:
            if year > 2025:
                # Investment from previous year
                electr_investment0 = self.V.read_var('dk_base', year, as_df=True, indexed=True)
                electr_investment0 = electr_investment0.reset_index().loc[electr_investment0.reset_index().PROD_COMM == 93]
                # FTT investment changes
                d_ftt_investment = ftt_model.investment[year].sum(axis = 1) / ftt_model.investment[year - 1].sum(axis = 1)
                # Apply growth rates
                electr_investment1 = electr_investment0.dk_base.values * d_ftt_investment
                msk = "PROD_COMM == 93"
                self.V.inject_var('dk_base', year + 1, electr_investment1, msk)

        print("--- {} run in: {} seconds ---".format(year,round(time.time() - year_time, 1)))
    
        # GLOBAL summary stats
        s_out = round((dq_total.sum() / IO_model.q_base.sum()) * 100, 2)
        s_gdp = round((dgdp_total.sum() / gdp_base.sum()) * 100, 2)
        # TODO employment
        s_emp = 0.0
        # s_emp = round((dempl_total.sum() / Prod_cost.empl_base['employment_base'].sum()) * 100, 2)
    
        print("##{}#####################################".format(year))
        print("OUT: {} | GDP: {} | EMP: {}".format(s_out, s_gdp, s_emp))
        print("###########################################")
        print("")

        if self.WRITE_AT_END:
            if year == self.model_end:
                self.V.generate_var_table(year)
            else:
                pass
        else:
            self.V.generate_var_table(year)
    
        #endregion

        return DYNAMIC, EXOG_VARS, CALIBRATING, MRIO_df_to_vec_DEF, \
            MRIO_vec_to_df_DEF, ftt_model, Log

# %%
