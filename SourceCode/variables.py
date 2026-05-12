"""
Created on 2024-08-29 18:20:16

@author: bkissdobronyi
"""

import os
import pandas as pd
import numpy as np
import inspect

from SourceCode.utils import logging

# ok, so the variable table basically stores variables in a number of numpy arrays
# all numpy arrays are ordered
# we have a basic write and read function

class variables_table:
    def __init__(self, log_:logging, scenario_name, model_start, model_end):
        self.log = log_
        self.scenario_name = scenario_name
        
        self.PATH = os.getcwd()
        dim_path = os.path.join(self.PATH, "Data", "MSET_data", "Variable_list_MINDSET.xlsx")
        var_path = os.path.join(self.PATH, "variables.xlsx")
        self.results_path = os.path.join(self.PATH, "Results")

        # we build the variables table
        var_data = pd.read_excel(var_path, "vars")

        # regions
        self.R = pd.read_excel(dim_path, 'R')
        self.R = self.R.sort_values(by="Lfd_Nr")
        self.R_list = self.R['Region_acronyms'].to_list()

        # sectors
        self.P = pd.read_excel(dim_path, 'P')
        self.P = self.P.sort_values(by="Lfd_Nr")
        self.P_list = self.P['Lfd_Nr'].to_list()

        # final demand
        self.FD_list = ['FD_1','FD_3','FD_4']

        self.var_data = var_data

        self.empty_tables_table = {}
        self.empty_tables = {}

        self.model_start = model_start
        self.model_end = model_end

        self.DIMS = {
            'REG_imp': self.R_list,
            'PROD_COMM': self.P_list,
            'REG_exp': self.R_list,
            'TRAD_COMM': self.P_list,
            'FD': self.FD_list
        }

        self.watch = ['employment_base']

        self.build_empty_tables(var_data)

        self.data = {}
        self.df_data = {}       # {var_name: {year: DataFrame}} — sparse/4D vars
        self.df_cache_size = 2  # max years kept in memory per variable

        # self.start_data_log()

    def build_empty_tables(self, var_data):
        # read in variable names from file
        var_list = var_data['VAR_NAME'].to_list()

        # get lists
        self.empty_tables_table = var_data[['VAR_NAME','DIM1','DIM2','DIM3','DIM4']].copy()
        var_empty_tables_df = self.empty_tables_table[['DIM1','DIM2','DIM3','DIM4']].drop_duplicates()
        var_empty_tables_df['id'] = range(len(var_empty_tables_df))
        self.empty_tables_table = self.empty_tables_table.merge(var_empty_tables_df, how='left', on=['DIM1','DIM2','DIM3','DIM4'])
        var_empty_tables_df = var_empty_tables_df.set_index('id')

        for i, r in var_empty_tables_df.iterrows():
            var_names = [x for x in r.tolist() if not pd.isnull(x)]
            var_lists = [self.DIMS[x] for x in var_names]
            self.empty_tables[i] = (
                pd.MultiIndex.from_product(var_lists, names=var_names)
                .to_frame(index=False)
            )

        return True
    
    def retrieve_empty_table(self, var_name):
        table_id = self.empty_tables_table[self.empty_tables_table['VAR_NAME']==var_name]['id'].values[0]
        df = self.empty_tables[table_id]
    
        return df
         
    def write_var(self, var_name, year, input_, from_df=False):
        """
        Write a variable's values into the object's data store for a given year, with optional
        alignment from a DataFrame and range validation.
        Parameters
        ----------
        var_name : str
            Name of the variable to write. This must exist in self.var_data and, when from_df
            is True, in self.empty_tables_table/self.empty_tables.
        year : Hashable (e.g., int or str)
            Key used to index into self.data[var_name] where the values will be stored.
        input_ : array-like or pandas.DataFrame
            If from_df is False: an array-like container (list, numpy array, pandas Series, etc.)
            containing the values for var_name in the correct order.
            If from_df is True: a pandas.DataFrame that contains at least the columns required
            to align with the target empty table plus a column named var_name. The method will
            merge this DataFrame with the target empty table to preserve row order and will
            fill missing values with 0 before extracting the variable column.
        from_df : bool, optional (default False)
            Interpret input_ as a DataFrame that must be merged with the relevant empty table
            to align rows and preserve ordering. When False, input_ is treated as a direct
            sequence of values.
        Returns
        -------
        bool
            True on success (values were written into self.data[var_name][year]).
        Side effects
        ------------
        - Stores the final values at self.data[var_name][year].
        - Reads metadata from:
            - self.empty_tables_table (to locate the table id for var_name when from_df=True)
            - self.empty_tables (the table used to align/merge input_ when from_df=True)
            - self.var_data (to obtain MAX/MIN validation thresholds for var_name)
        - Attempts to copy out-of-range input values to the system clipboard before raising
          a ValueError (via pandas' to_clipboard).
        Validation and errors
        ---------------------
        - The method checks that all values lie within the range [MIN, MAX] for var_name as
          defined in self.var_data. Null MAX is treated as +inf and null MIN as -inf.
        - If any value is outside the allowed range, a ValueError is raised and the
          offending values are sent to the clipboard (for debugging).
        - The method may raise KeyError/IndexError/AttributeError if expected metadata entries
          or tables are missing or if var_name is not found in the expected structures.
        Notes
        -----
        - input_ is shallow-copied at the start to avoid mutating the caller's object.
        - When from_df is True, the function merges the provided DataFrame with the
          corresponding "empty table" to ensure the output vector has the same ordering and
          length as the target table, with missing values filled as zero.
        """

        # write a variable, if df, check order
        if from_df:
            table_id = self.empty_tables_table[self.empty_tables_table['VAR_NAME']==var_name]['id'].values[0]
            # keep only relevant vars
            df = self.empty_tables[table_id]
            df = df.merge(input_[df.columns.tolist() + [var_name]], how='left').fillna(0)
            input_use = df[var_name].values
        else:
            input_use = input_.copy()

        # TODO need to do dimension check (productivity!!!!)
        
        # first check validation
        # if var_name == "shadow_unemployment_rate":
            # import pdb; pdb.set_trace()

        max_ = self.var_data[self.var_data["VAR_NAME"]==var_name]['MAX'].values[0]
        min_ = self.var_data[self.var_data["VAR_NAME"]==var_name]['MIN'].values[0]
        max_ = max_ if ~pd.isnull(max_) else np.inf
        min_ = min_ if ~pd.isnull(min_) else -np.inf
        if np.max(input_use) > max_ or np.min(input_use) < min_:
            print(f"Validation error: {inspect.stack()[1][3]} - #{inspect.stack()[1][2]}")
            import pdb; pdb.set_trace()
            raise ValueError("Validation failed for variable: {}; values sent to clipboard".format(var_name))
        
        if var_name in self.data.keys(): 
            self.data[var_name][year] = input_use
        else:
            self.data[var_name] = {}
            # create NA for years where not present
            years = np.arange(self.model_start-3, year)
            for y in years:
                self.data[var_name][y] = np.full_like(input_use, np.nan)
            self.data[var_name][year] = input_use

        if var_name in self.watch:
            self.log_series(var_name, year, label=f"{inspect.stack()[1][3]} - #{inspect.stack()[1][2]}")

        return True
    
    def inject_var(self, var_name, year, input_, mask=None, from_df=False):
        # ? mask as string, i.e., PROD_COMM == 93
        # ? input can be 
        # ?      [1] df with dimensions (no mask)
        # ?      [2] scalar with mask

        if (mask is None) and (from_df == False):
            raise TypeError("Scalar inject needs mask")
        elif(from_df == True) and (mask is not None):
            raise TypeError("DF inject does not take mask")
        else:
            pass

        if from_df:
            input_use = input_.copy()
        else:
            input_use = input_
        
        table_id = self.empty_tables_table[self.empty_tables_table['VAR_NAME']==var_name]['id'].values[0]
        # slice table
        if not (mask is None):
            df = self.empty_tables[table_id].query(mask).copy()
        else:
            df = self.empty_tables[table_id]

        # if df
        if from_df:
            df = df.merge(input_[df.columns.tolist() + [var_name]], how='left', on=df.columns.tolist())
            df = df[~df[var_name].isna()].copy()
        else:
            df[var_name] = input_use
        idxs = df.index.to_list()
        input_use = df[var_name].values

        # first check validation
        max_ = self.var_data[self.var_data["VAR_NAME"]==var_name]['MAX'].values[0]
        min_ = self.var_data[self.var_data["VAR_NAME"]==var_name]['MIN'].values[0]
        max_ = max_ if ~pd.isnull(max_) else np.inf
        min_ = min_ if ~pd.isnull(min_) else -np.inf
        if np.max(input_use) > max_ or np.min(input_use) < min_:
            print(f"Validation error: {inspect.stack()[1][3]} - #{inspect.stack()[1][2]}")
            import pdb; pdb.set_trace()
            raise ValueError("Validation failed for variable: {}; values sent to clipboard".format(var_name))
        
        self.data[var_name][year][idxs] = input_use

        if var_name in self.watch:
            self.log_series(var_name, year, label=f"{inspect.stack()[1][3]} - #{inspect.stack()[1][2]}")

        return True

    def read_var(self, var_name, year, as_df=False, indexed=False):
        """
        Read a variable for a given year from the object's data store.
        Parameters
        ----------
        var_name : str
            Name of the variable to read.
        year : int or str
            Year index (or key) to read from the variable's data.
        as_df : bool, optional
            If False (default), return the raw slice self.data[var_name][year].
            If True, return a DataFrame obtained by concatenating a corresponding
            empty table (looked up via self.empty_tables_table['VAR_NAME'] == var_name)
            and the variable slice renamed to var_name. The empty table id is taken
            from the first matching row's 'id'.
        Returns
        -------
        pandas.Series or pandas.DataFrame
            The variable data for the requested year. When as_df is True, returns a
            DataFrame built from the empty table and the variable data.
        Raises
        ------
        KeyError
            If var_name or year is not present in self.data.
        IndexError
            If no matching empty table entry is found for var_name in self.empty_tables_table.
        Notes
        -----
        This method expects:
        - self.data to be indexable as self.data[var_name][year],
        - self.empty_tables_table to contain 'VAR_NAME' and 'id' columns,
        - self.empty_tables to be indexable by the id values from self.empty_tables_table.
        """

        ret = self.data[var_name][year]
        # if need to be returned as DF
        if as_df:
            # first look up empty table
            table_id = self.empty_tables_table[self.empty_tables_table['VAR_NAME']==var_name]['id'].values[0]
            df = pd.concat([self.empty_tables[table_id],pd.Series(ret).rename(var_name)], axis=1)
            ret = df
            if indexed:
                ret = ret.set_index(self.empty_tables[table_id].columns.to_list())

        return ret

    def write_var_df(self, var_name, year, df):
        """
        Write a sparse/4D DataFrame variable. Persists to parquet immediately and
        keeps the two most recent years in memory; older years are evicted from the
        cache (parquet on disk remains available for read_var_df).
        """
        # Validate variable is registered in variables.xlsx
        if var_name not in self.var_data['VAR_NAME'].values:
            raise ValueError(f"write_var_df: '{var_name}' is not registered in variables.xlsx")

        # Validate that all expected dimension columns are present in the DataFrame
        var_row = self.var_data[self.var_data['VAR_NAME'] == var_name].iloc[0]
        expected_dims = [var_row[d] for d in ('DIM1', 'DIM2', 'DIM3', 'DIM4') if not pd.isnull(var_row[d])]
        missing_dims = [d for d in expected_dims if d not in df.columns]
        if missing_dims:
            raise ValueError(f"write_var_df: '{var_name}' DataFrame is missing expected dimension columns {missing_dims}")

        # Validate that values in each dimension column are within the allowed set
        for dim in expected_dims:
            if dim in self.DIMS:
                invalid_values = set(df[dim].unique()) - set(self.DIMS[dim])
                if invalid_values:
                    raise ValueError(f"write_var_df: '{var_name}' column '{dim}' contains values not in dimension definition: {invalid_values}")

        # Persist to results folder following generate_var_table naming convention
        parquet_path = os.path.join(
            self.results_path,
            f"results_file_long_{self.scenario_name}_{var_name}_{year}.parquet"
        )
        df.to_parquet(parquet_path, index=False)

        # Store in memory cache
        if var_name not in self.df_data:
            self.df_data[var_name] = {}
        self.df_data[var_name][year] = df

        # Evict years beyond the cache limit (keep most recent df_cache_size years)
        cached_years = sorted(self.df_data[var_name].keys())
        while len(cached_years) > self.df_cache_size:
            del self.df_data[var_name][cached_years.pop(0)]

    def read_var_df(self, var_name, year):
        """
        Read a sparse/4D DataFrame variable. Serves from memory cache if available,
        otherwise loads the corresponding parquet from disk without re-caching.
        """
        if var_name in self.df_data and year in self.df_data[var_name]:
            return self.df_data[var_name][year]

        parquet_path = os.path.join(
            self.results_path,
            f"results_file_long_{self.scenario_name}_{var_name}_{year}.parquet"
        )
        return pd.read_parquet(parquet_path)

    def generate_var_table(self, year):
        groups_ = self.empty_tables_table[['VAR_NAME','id']].groupby(['id'])
        for k in groups_.groups.keys():
            vars_ = groups_.get_group(k)['VAR_NAME'].to_list()

            empty = self.empty_tables[k]
            years = np.arange(self.model_start-3, year+1)

            # select variables that are present
            what_we_want = set(vars_)
            what_we_have = set(self.data.keys())
            print_ = list(what_we_have.intersection(what_we_want))

            year_dfs = []

            for y in years:
                print_vector = [(self.data[x][y]) if (y in self.data[x].keys()) else np.full(empty.shape[0], np.nan) for x in print_]
                year_df = empty.copy()
                year_df['year'] = y
                print_df = pd.DataFrame(print_vector).T
                print_df.columns = print_
                year_df = pd.concat([year_df, print_df], axis=1)
                year_dfs.append(year_df)

            res_table = pd.concat(year_dfs, axis=0, ignore_index=True)
            res_table = res_table

            # import pdb; pdb.set_trace()
            # for v in vars_:
            #     try:
            #         df_ = pd.DataFrame(self.data[v]).assign(var_name = v)
            #         var_out = pd.concat([empty, df_.reset_index(drop=True)], axis=1)
            #         var_out = pd.melt(var_out, id_vars=empty.columns.to_list() + ['var_name'], var_name='year', value_name='value')
            #         res_table = pd.concat([res_table, var_out], axis=1)
            #         # ? write zeros?
            #         # print_zero = self.var_data[self.var_data["VAR_NAME"]==v]['PRINT_ZERO'].values[0]
            #         # print_zero = True if print_zero == 'TRUE' else False
            #         # if print_zero:
            #             # res_table = res_table[res_table['value']!=0].copy()
            #     except KeyError:
            #         print(f"Printing results >>>>> {v} is not present. Skipping.")
            #         pass

            # ? if more than two dimensions use parquet
            if empty.shape[1] > 2:
                res_table.to_parquet(os.path.join(self.results_path, f"results_file_long_{self.scenario_name}_{k}.parquet"), index=False)
            else:
                res_table.fillna('NA').to_csv(os.path.join(self.results_path, f"results_file_long_{self.scenario_name}_{k}.csv"), index=False)

    def log_series(self, var_name, year, label="N/A"):
        d_ = self.read_var(var_name, year, as_df=True, indexed=True)
        d_ = d_.rename(columns={var_name:f"{year} - {label}"})
        self.log.log_to_csv(var_name, d_, append="vertical")