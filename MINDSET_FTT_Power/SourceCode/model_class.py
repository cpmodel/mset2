# -*- coding: utf-8 -*-
"""
=========================================
model_class.py
=========================================

Model Class file for MSET-coupled FTT:Power.


ModelRun class: main class for operation of model.

"""

# Standard library imports
import configparser
import logging
from pathlib import Path

# Third party imports
import numpy as np
from tqdm import tqdm

from ftt_source.paths import set_paths
from ftt_source.Power.ftt_p_main import solve as ftt_p_solve, build_power_settings

from ftt_source.support.data_loading import load_data
from ftt_source.support.titles_functions import load_titles
from ftt_source.support.dimensions_functions import load_dims
from ftt_source.support.cross_section import cross_section as cs


class ModelRun:
    """
    Class to run the FTT model.

    Class object is a single run of the model.

    Local library imports:

        FTT modules:

        - `FTT: Power <ftt_p_main.html>`__
            Power generation FTT module


        Support functions:

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
    dims: dict of lists of str
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

    def __init__(self, model_end, scenario):
        """ Instantiate model run object

        model_end: int. Final year of the run, supplied by MSET scenario file
        so that both models share the same timeline.
        """

        # Attributes given in settings.ini file
        _mindset_root = Path(__file__).parents[1]
        _settings_ini = str(_mindset_root / 'settings.ini')
        config = configparser.ConfigParser()
        config.read(_settings_ini)
        self.name = config.get('settings', 'name')
        self.model_start = int(config.get('settings', 'model_start'))
        self.model_end = int(model_end)
        self.simulation_start = int(config.get('settings', 'simulation_start'))
        self.simulation_end = self.model_end
        self.current = self.model_start
        self.years = np.arange(self.model_start, self.model_end+1)
        self.timeline = np.arange(self.simulation_start, self.simulation_end+1)
        self.ftt_modules = config.get('settings', 'enable_modules')
        self.scenarios = scenario

        # Point FTT_Standalone at MINDSET's Utilities and settings (once at startup)
        set_paths(inputs_path=_mindset_root / 'Inputs', utilities_path=_mindset_root / 'Utilities')
        self.ftt_settings_path = _settings_ini

        # Load classification titles
        self.titles = load_titles()
        self.power_settings = build_power_settings(self.titles, config)

        # Load variable dimensions
        self.dims, self.histend, self.domain, self.forstart, self.units = load_dims()

        # Retrieve inputs; scenarios without input files fall back to S0
        self.input = load_data(self.titles, self.dims, self.timeline,
                               scenario, self.ftt_modules, self.forstart)
        if scenario not in self.input:
            logging.getLogger(__name__).warning(
                "FTT:Power scenario '%s' has no input files; using S0 inputs.", scenario,
            )
            self.input[scenario] = {
                var: values.copy() for var, values in self.input['S0'].items()
            }

        # Initialize remaining attributes
        self.variables = {}
        self.lags = {}
        # Define output container
        self.output = {scen: {var: np.full_like(self.input[scen][var], 0) \
                              for var in self.input[scen]} for scen in self.input}

        # Carbon price coupling state (MSET-coupled mode only).
        # Written by ftt_power.py before each solve_year(); consumed in solve_year().
        # Shape (n_reg,): one regional carbon price in USD2023/tCO2.
        self._mset_reppx = None

        # Fuel price coupling state (MSET-coupled mode only).
        # _mset_fuel_price_index_change is written by ftt_power.py before each solve_year() call.
        # _fpix_carry accumulates the cumulative price index across years.
        self._mset_fuel_price_index_change = None
        self._fpix_carry = np.ones((len(self.titles['RTI']), len(self.titles['T2TI'])))

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
                    self.store_output(y, scen)

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

            # MSET's carbon price has already been converted to USD2023/tCO2.
            if self._mset_reppx is not None:
                variables['CO2taxP'] = self._mset_reppx.copy()
                self._mset_reppx = None   # consume : must be re-set each year by ftt_power.py

            # Overwrite BCET's '22 Gamma' column with MGAM before calling FTT_Standalone.
            if 'MGAM' in variables:
                c2ti_m = {cat: idx for idx, cat in enumerate(self.titles['C2TI'])}
                variables['BCET'][:, :, c2ti_m['22 Gamma']] = variables['MGAM']

            # FPIX is cumulative fuel price index; _fpix_carry persists it. None = standalone (no change).
            fuel_price_index_change = self._mset_fuel_price_index_change if self._mset_fuel_price_index_change is not None else 0.0
            self._mset_fuel_price_index_change = None   # consume : must be re-set each year by ftt_power.py
            if 'FPIX' in variables:
                fpix_lag = np.where(self._fpix_carry == 0, 1.0, self._fpix_carry)
                variables['FPIX'] = fpix_lag * (1.0 + fuel_price_index_change)
                self._fpix_carry  = variables['FPIX'].copy()

            # Call FTT_Standalone
            variables = ftt_p_solve(
                variables, time_lags, self.titles, self.histend,
                tl[y], self.domain, self.power_settings
            )

        if not any(True for x in modules_list if x in self.ftt_modules):
            print("Incorrect selection of modules. Check settings.ini")

        return variables, time_lags

    def store_output(self, y, scenario):
        """Store solved variables for year index y in the output container."""
        for variable, values in self.variables.items():
            target = self.output[scenario][variable]
            dimensions = self.dims[variable]
            if 'TIME' in dimensions:
                index = [slice(None)] * target.ndim
                index[dimensions.index('TIME')] = y
                target[tuple(index)] = values
            else:
                target[...] = values

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
