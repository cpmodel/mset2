# -*- coding: utf-8 -*-
"""
=========================================
model_class.py
=========================================

Model Class file for FTT Stand alone.


ModelRun class: main class for operation of model.

"""

# Standard library imports
import configparser
from pathlib import Path

# Third party imports
import numpy as np
from tqdm import tqdm

from ftt_source.paths import set_paths
from ftt_source.Power.ftt_p_main import solve as ftt_p_solve

# Support modules
import MINDSET_FTT_Power.SourceCode.support.input_functions as in_f
import MINDSET_FTT_Power.SourceCode.support.titles_functions as titles_f
import MINDSET_FTT_Power.SourceCode.support.dimensions_functions as dims_f
from MINDSET_FTT_Power.SourceCode.support.cross_section import cross_section as cs
# from SourceCode.initialise_csv_files import initialise_csv_files


class ModelRun:
    """
    Class to run the FTT model.

    Class object is a single run of the model.

    Local library imports:

        FTT modules:

        - `FTT: Power <ftt_p_main.html>`__
            Power generation FTT module


        Support functions:

        - `paths_append <paths_append.html>`__
            Appends file path to sys path to enable import
        - `divide <divide.html>`__
            Bespoke element-wise divide which replaces divide-by-zeros with zeros

    Attributes
    -----------
    name: str
        Name of model run, and specification file read
    hist_start: int
        Starting year of the historical data
    model_start: int
        First year of model timeline
    model_end: int
        Final year of model timeline
    current: int
        Curernt/active year of solution
    years: tuple of (int, int)
        Bookend years of model_timeline
    timeline: list of int
        Years of the model timeline
    titles: dictionary of lists
        Dictionary containing all title classifications
    dims: dict of tuples (str, str, str, str)
        Variable classifications by dimension
    histend: dict of integers
        Final year of histrorical data by variable
    specs: dictionary of NumPy arrays
        Function specifications for each region and module
    input: dictionary of NumPy arrays
        Dictionary containing all model input variables
    variables: dictionary of NumPy arrays
        Dictionary containing all model variables for a given year of solution
    lags: dictionary of NumPy arrays
        Dictionary containing lag variables
    output: dictionary of NumPy arrays
        Dictionary containing all model variables for output



    """

    def __init__(self):
        """ Instantiate model run object """

        # Attributes given in settings.ini file
        _mindset_root = Path(__file__).parents[1]
        _settings_ini = str(_mindset_root / 'settings.ini')
        config = configparser.ConfigParser()
        config.read(_settings_ini)
        self.name = config.get('settings', 'name')
        self.model_start = int(config.get('settings', 'model_start'))
        self.model_end = int(config.get('settings', 'model_end'))
        self.simulation_start = int(config.get('settings', 'simulation_start'))
        self.simulation_end = int(config.get('settings', 'simulation_end'))
        self.current = self.model_start
        self.years = np.arange(self.model_start, self.model_end+1)
        self.timeline = np.arange(self.simulation_start, self.simulation_end+1)
        self.ftt_modules = config.get('settings', 'enable_modules')
        self.scenarios = config.get('settings', 'scenarios')

        # Point FTT_Standalone at MINDSET's Utilities and settings (once at startup)
        set_paths(utilities_path=str(_mindset_root / 'Utilities'))
        self.ftt_settings_path = _settings_ini
        self.carbon_price_conv_factor = float(
            config.get('settings', 'carbon_price_conv_factor', fallback='1.3281'))
        # Read exchange-rate variable names from settings (must match ftt_p_main.py)
        _ex_base_year = int(config.get('settings', 'ex_base_year', fallback='2018'))
        self._prsc_ex_var = f"PRSC{str(_ex_base_year)[2:]}"   # e.g. "PRSC18"
        self._ex_var      = f"EX{str(_ex_base_year)[2:]}"     # e.g. "EX18"

        # Load classification titles
        self.titles = titles_f.load_titles()
        self.conv = titles_f.load_converters()

        # Load variable dimensions
        self.dims, self.histend, self.domain, self.forstart = dims_f.load_dims()

        # Retrieve inputs ÔÇö C2TI size must match the CSV files at this point
        self.input = in_f.load_data(self.titles, self.dims, self.timeline,
                                    self.scenarios, self.ftt_modules,
                                    self.forstart)

        # After loading, extend BCET and C2TI so FTT_Standalone's ftt_p_lcoe can find
        # '22 Gamma' (index 21) and '23 Value factor' (index 22) by name.
        # The CSV data ends at '21 Gamma ($/MWh)' (index 20); we copy it to column 21
        # and default Value factor to 1.0 for all technologies.
        c2ti_list = list(self.titles['C2TI'])
        gamma_col = c2ti_list.index('21 Gamma ($/MWh)')  # index 20
        new_entries = [e for e in ('22 Gamma', '23 Value factor') if e not in c2ti_list]
        if new_entries:
            n_extra = len(new_entries)
            for scen in self.input:
                bcet = self.input[scen]['BCET']          # (RTI, T2TI, C2TI, 1)
                extra = np.ones((bcet.shape[0], bcet.shape[1], n_extra, bcet.shape[3]))
                extra[:, :, 0, :] = bcet[:, :, gamma_col, :]   # '22 Gamma' = copy of col 21
                # '23 Value factor' stays 1.0
                self.input[scen]['BCET'] = np.concatenate([bcet, extra], axis=2)
            c2ti_list.extend(new_entries)
            self.titles['C2TI'] = tuple(c2ti_list)


        # Initialize remaining attributes
        self.variables = {}
        self.lags = {}
        # Define output container
        self.output = {scen: {var: np.full_like(self.input[scen][var], 0) \
                              for var in self.input[scen]} for scen in self.input}

        # Carbon price coupling state (MSET-coupled mode only).
        # Written by ftt_power.py before each solve_year(); consumed in solve_year().
        # Shape (n_reg, n_tech, 1) ÔÇö one ctax per (region, technology) in EUR2015/tCO2.
        self._mset_reppx = None

        # Fuel price coupling state (MSET-coupled mode only).
        # _mset_fpi is written by ftt_power.py before each solve_year() call.
        # _fpix_carry accumulates the cumulative price index across years.
        self._mset_fpi   = None
        self._fpix_carry = np.ones((len(self.titles['RTI']), len(self.titles['T2TI']), 1))

    def run(self):
        """ Solve model run and save results """

        # Run the solve all method (self.input contains all results)
        self.solve_all()

    def solve_all(self):
        """ Solve model for each year of the simulation period """


        # self.output = copy.deepcopy(self.input)

        # Clear any previous instances of the progress bar
        try:
            tqdm._instances.clear()
        except AttributeError:
            pass
        for scen in self.input:

            # Create progress bar:
            with tqdm(self.timeline) as pbar:

            # Call solve_year method for each year of the simulation period
#                for year_index, year in enumerate(self.timeline):
                for y, year in enumerate(self.timeline):
                    # Set the description to be the current year
                    pbar.set_description(f'Running Scenario: {scen} - Solving year: {year}')

                    self.variables, self.lags = self.solve_year(year, y, scen)

                    # Increment the progress bar by one step
                    pbar.update(1)

                    # Populate output container
                    for var in self.variables:
                        if 'TIME' in self.dims[var]:
                            self.output[scen][var][:, :, :, y] = self.variables[var]
                        else:
                            self.output[scen][var][:, :, :, 0] = self.variables[var]

            # Set the progress bar to say it's complete
            pbar.set_description(f"Model run {self.name} finished")

    def solve_year(self, year, y, scenario, max_iter=1):
        """ Solve model for a specific year """

        # Need to add a convergence check here in the future

        # Run update
        variables, time_lags = self.update(year, y, scenario)

        # Define whole period
        tl = self.timeline

        # define modules list in for possible setting.ini selection
        modules_list = ["FTT-P"]

        if "FTT-P" in self.ftt_modules:

            # Convert MINDSET ctax (EUR2015/tCO2) to CO2taxP (USD2013/tCO2).
            # Use time_lags for exchange-rate snapshots: variables has them as zero (no CSV in coupled Inputs).
            if self._mset_reppx is not None:
                _prsc18 = time_lags.get(self._prsc_ex_var)
                _ex18   = time_lags.get(self._ex_var)
                if _prsc18 is not None and _ex18 is not None:
                    denom = (variables['PRSCX'] * _ex18
                             / np.maximum(_prsc18 * variables['EXX'], 1e-10))
                    variables['CO2taxP'] = (self._mset_reppx * self.carbon_price_conv_factor
                                            / np.where(denom != 0, denom, 1.0))
                self._mset_reppx = None   # consume ÔÇö must be re-set each year by ftt_power.py

            # Overwrite BCET's '22 Gamma' column with MGAM before calling FTT_Standalone.
            if 'MGAM' in variables:
                c2ti_m = {cat: idx for idx, cat in enumerate(self.titles['C2TI'])}
                n_c2ti = len(self.titles['C2TI'])   # 23 after __init__ extension
                for d in (variables, time_lags):
                    if d['BCET'].shape[2] < n_c2ti:
                        ext = np.zeros((*d['BCET'].shape[:2], n_c2ti))
                        ext[:, :, :d['BCET'].shape[2]] = d['BCET']
                        d['BCET'] = ext
                variables['BCET'][:, :, c2ti_m['22 Gamma']] = variables['MGAM'][:, :, 0]

            # FPIX is cumulative fuel price index; _fpix_carry persists it. None = standalone (no change).
            fpi = self._mset_fpi if self._mset_fpi is not None else 0.0
            self._mset_fpi = None   # consume ÔÇö must be re-set each year by ftt_power.py
            if 'FPIX' in variables:
                fpix_lag = np.where(self._fpix_carry == 0, 1.0, self._fpix_carry)
                variables['FPIX'] = fpix_lag * (1.0 + fpi)
                self._fpix_carry  = variables['FPIX'].copy()

            # Call FTT_Standalone (drops iter_lag and conv; adds settings_path)
            variables = ftt_p_solve(
                variables, time_lags, self.titles, self.histend,
                tl[y], self.domain, settings_path=self.ftt_settings_path
            )

        if not any(True for x in modules_list if x in self.ftt_modules):
            print("Incorrect selection of modules. Check settings.ini")

        return variables, time_lags

    def update(self, year, y, scenario):
        """ Update model variables for a new year of solution """

        # Update the current year attribute
        self.current = year

        # Set any required variables as equal to the previous year
        # This is how E3ME solves a number of variables, return to this

        # Read required variables from the cross section
        # This is how E3ME solves a number of variables, return to this
        data_to_model = cs(self.input, self.dims, year, y, scenario)

        # LB TODO: to improve the treatment of lags to include also historical data
        if y == 0: # If year is the first year, lags equal variables in starting year
            lags = cs(self.input, self.dims, year, y, scenario)
        else:
            #lags = cs(self.variables, self.dims, year-1)
            lags = self.variables

        return data_to_model, lags
