"""
Created on 2024-04-08 13:35:39

@author: bkissdobronyi
"""

import os
import re
import shutil
import pickle
import glob
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from scipy import sparse


def atomic_pickle_dump(obj, path):
    """Pickle to `path` so concurrent readers never see a partially written file."""
    tmp_path = f"{path}.{os.getpid()}.tmp"
    with open(tmp_path, 'wb') as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp_path, path)


class run_paths:
    """Per-run directories so several runs can share one checkout concurrently.

    Every run gets an id, `{timestamp}_{scenario_name}[_{suffix}]` unless `run_id` is given
    (an explicit `run_id` is used as is, `suffix` is ignored), and its own
    Temp/<id>, Log/<id> and Results/<id> (FTT output goes to Results/<id>/ftt_output). The
    Results/<id> folder is created with exist_ok=False, which is what claims the id: a clash
    between two auto-generated ids gets a numeric suffix, an explicit `run_id` that already
    exists raises instead of overwriting another run's output.
    """
    def __init__(self, scenario_name, run_id=None, base=".", suffix=None):
        explicit = run_id is not None
        if not explicit:
            run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{scenario_name}"
            # the suffix becomes part of a folder name: keep it filesystem-safe
            suffix = re.sub(r"[^A-Za-z0-9._-]+", "_", suffix.strip()) if suffix else ""
            if suffix:
                run_id = f"{run_id}_{suffix}"

        n = 1
        while True:
            candidate = run_id if n == 1 else f"{run_id}_{n}"
            results_dir = os.path.join(base, "Results", candidate)
            try:
                os.makedirs(results_dir)
                break
            except FileExistsError:
                if explicit:
                    raise
                n += 1

        self.run_id = candidate
        self.results_dir = results_dir
        self.temp_dir = os.path.join(base, "Temp", candidate)
        self.log_dir = os.path.join(base, "Log")
        self.ftt_dir = os.path.join(results_dir, "ftt_output")
        for d in (self.temp_dir, self.ftt_dir):
            os.makedirs(d, exist_ok=True)


class temporary_storage:
    def __init__(self, path="Temp"):
        self.PATH = path
        os.makedirs(self.PATH, exist_ok=True)

    def cleanup(self):
        """Remove the whole storage folder (used once a run has finished)."""
        shutil.rmtree(self.PATH, ignore_errors=True)

    def save_to_pickle(self, obj, write_name):
        with open(os.path.join(self.PATH, f"{write_name}.pkl"), 'wb') as write_file:
            pickle.dump(obj, write_file, protocol=pickle.HIGHEST_PROTOCOL)
        return True
            
    def read_from_pickle(self, obj_name, delete_=True):
        ret_ = None
        with open(os.path.join(self.PATH, f"{obj_name}.pkl"), 'rb') as read_file:
            ret_ = pickle.load(read_file)
        if delete_:
            os.remove(os.path.join(self.PATH, f"{obj_name}.pkl"))
        return ret_
    
    def delete_all(self):
        files = glob.glob(os.path.join(self.PATH, "*"))
        for f in files:
            os.remove(f)

    def write_to_csv(self, df, write_name):
        df.to_csv(os.path.join(self.PATH, f"{write_name}.csv"), index=False)


class logging:
    def __init__(self, path="Log", subdir=None):
        self.PATH = os.path.join(path, subdir if subdir else self.get_time_str())
        # p = Path(self.PATH).resolve()
        # p.mkdir(parents=True, exist_ok=True)
        Path(self.PATH).mkdir(parents=True, exist_ok=True)

    def get_time_str(self, sec=False):
        now = datetime.now()
        if sec:
            dt_string = now.strftime("%d%m%Y_%H%M%S")
        else:
            dt_string = now.strftime("%d%m%Y_%H%M")
        return dt_string
    
    def log_to_csv(self, name:str, df_:pd.DataFrame, append=False, timestamp=True):
        if append == "horizontal":
            df_.to_csv(os.path.join(self.PATH, f"{name}.csv"), mode='a', header=False)
        elif append == "vertical":
            try:
                df_prev = pd.read_csv(os.path.join(self.PATH, f"{name}.csv"))
                write_df = pd.concat([df_prev, df_.reset_index(drop=True)], axis=1)
                write_df.to_csv(os.path.join(self.PATH, f"{name}.csv")) 
            except FileNotFoundError:
                df_.reset_index().to_csv(os.path.join(self.PATH, f"{name}.csv"))
        else:
            df_.to_csv(os.path.join(self.PATH, f"{name}.csv"))

    def log_to_txt(self, message:str, name:str, append=True):

        # TODO: there is no overwrite just append
        with open(os.path.join(self.PATH, f"{name}.txt"), 'a') as f:
            f.write(f"{self.get_time_str(sec=True)}\t{message}\n")


def resolve_hyphen(df_:pd.DataFrame, col_name:str):
    """Function to resolve hyphens in dataframe cells. Generates a long format 
    dataframe where cells with hyphens between numerics (e.g., 10-12) are
    turned into multiple rows (e.g., 1st row: 10, 2nd row: 11, 3rd: 12). 
    Used mostly to turn manually inputed scenario sector codes into long form 
    scenario specifications. 

    Parameters
    ----------
    df_ : pd.DataFrame
        dataframe to transform
    col_name : string
        name of the column to search for cells with hyphens

    Returns
    -------
    pd.DataFrame
        dataframe with numeric hyphen cells expanded
    """    
    df = df_.copy().reset_index(drop=True)
    df.loc[:,col_name] = df[col_name].astype(str)
    
    if len(df) > 0:
        temp_new = df[col_name].str.extract(r"([0-9]{1,})-([0-9]{1,})", expand=False).fillna(0)
        df['new'] = temp_new.apply(lambda r: np.arange(int(r[0]),int(r[1])+1).tolist() if r[0] != 0 else np.nan, axis=1)
    
        df.loc[~df['new'].isna(), col_name] = df.loc[~df['new'].isna(), 'new']
        df = df.drop(columns=['new'])
        df = df.explode(col_name)
        df = df.astype({col_name:'str'})

    return df

def resolve_comma(df_:pd.DataFrame, col_name:str):
    """Function to resolve commas in dataframe cells. Generates a long format
    dataframe where cells with commas between numerics or strings (e.g., 1,4,6 or
    IND,AFG,PAK) are turned into multiple rows (duplicating cells in the other 
    columns). Used mostly to turn manually inputed scenario codes into long
    form scenario specifications.

    Parameters
    ----------
    df_ : pd.DataFrame
        dataframe to transform
    col_name : str
        name of the column to search for cells with commas

    Returns
    -------
    pd.Dataframe
        dataframe with commas cells expanded
    """    
    df = df_.copy()
    df.loc[:,col_name] = df[col_name].astype(str)
    
    if len(df) > 0:
        df['new'] = np.nan
        
        sel = df[col_name].str.contains(",")
        df.loc[sel, 'new'] = df.loc[sel, col_name].str.split(',')
    
        df.loc[~df['new'].isna(), col_name] = df.loc[~df['new'].isna(), 'new']
        df = df.drop(columns=['new'])
        df = df.explode(col_name)
        df = df.astype({col_name:'str'})

    return df

def resolve_all(df_:pd.DataFrame, col_name:str, all_:list):
    """Resolves 'ALL' in the selected column to the specified list (all_)
    replicating all other column values. 

    Parameters
    ----------
    df_ : pd.DataFrame
        dataframe to transform
    col_name : str
        selected column, which could contain 'ALL'
    all_ : list
        replace values in the selected column with these

    Returns
    -------
    pd.DataFrame
        resolved dataframe
    """    
    
    df = df_.copy()
    if len(df) > 0:

        col_names_excl_selected = [x for x in df.columns if x != col_name]
        pairs = df[df[col_name]=='ALL'][col_names_excl_selected].copy()
        if len(pairs) > 0:
            pairs['key'] = 1
            keys = pd.DataFrame({
                col_name: all_,
                'key': 1
            })
            complement_ALL = keys.merge(pairs, how='left', on='key')
            complement_ALL = complement_ALL.drop(columns=['key'])
            df = pd.concat([df[df[col_name]!='ALL'], complement_ALL])

    return df


# MRIO functions

def attach_iso3(df, regions, target=True, origin=False):
        """ 
        Attaches ISO3 codes from the `regions` input to the dataframe
        `origin-country` and `target-country` have to be present in the dataframe
        """
        regions = regions.drop(columns=['Region_names'])
        regions['Region_acronyms'] = regions['Region_acronyms'].astype('category')
        if target:
            df = df.merge(regions, how='left', left_on=['target-country'], right_on=['Lfd_Nr']).rename(columns={'Region_acronyms':'target-country-iso3'})\
                .drop(columns=['Lfd_Nr'])
        if origin:
            df = df.merge(regions, how='left', left_on=['origin-country'], right_on=['Lfd_Nr']).rename(columns={'Region_acronyms':'origin-country-iso3'})\
                .drop(columns=['Lfd_Nr'])
        return df
    
def MRIO_vec_to_df(vector:np.ndarray, name:str, products:int, iso3:object=[]):
    """Converts and MRIO vector (which should have length 164x120) into
    a long-form dataframe

    Parameters
    ----------
    vector : np.ndarray
        input vector must be 19680 in length
    name : str
        name of the vector
    iso3 : object, optional
        whether to convert regions to ISO3 names, either `False` or 
        provide regions in pd.DataFrame, by default False

    Returns
    -------
    pd.DataFrame
        returns dataframe of the vector, columns:
        | target-country | target-sector | [name] | target-country-iso3 (optional) |
    """
    # vector is 19680, 120x164
    vec = pd.DataFrame(vector.T).reset_index()
    vec.columns = ['index', name]
    vec['target-country'] = (np.floor(vec['index'] / products)).astype('int16') + 1
    vec['target-sector'] =  (vec['index'] % products).astype('int16') + 1
    vec[name] = vec[name].astype('float32')
    vec = vec.drop(columns=['index'])

    if len(iso3) > 0: # type: ignore
        vec = attach_iso3(vec, iso3)

    return vec

def MRIO_df_to_vec(df:pd.DataFrame, country_col:str, sector_col:str, value_col:str,
                   countries_inorder:list, sectors_inorder:list, default_value=0.0):
    """Convert a df with country and sector dimensions to a 19680 (120x164) vector.

    Parameters
    ----------
    df : pd.DataFrame
        input dataframe with dimensions specified in further arguments
    country_col : str
        country column
    sector_col : str
        sector column
    value_col : str
        value column (dy)

    Returns
    -------
    np.ndarray
        vector to return (dy), 120x164
    """    
    # import REG_imp | TRAD_COMM | PROD_COMM [FD_1] | dy
    df_ = df.copy().astype({sector_col:'str'})
    df_ = df_.rename({sector_col:'PROD_COMM',country_col:'REG_imp'})
    df_ = df_.groupby([country_col, sector_col]).agg({value_col:'sum'})

    # construct base to fill out
    df_empty = pd.DataFrame({
        'REG_imp': np.repeat(countries_inorder, len(sectors_inorder)),
        'PROD_COMM': np.tile(sectors_inorder, len(countries_inorder))
    })
    df_empty['dy'] = default_value
    df_empty = df_empty.astype({'PROD_COMM':'str'})
    df_empty = df_empty.set_index(['REG_imp','PROD_COMM'])

    df_empty.loc[df_.index, 'dy'] = df_[value_col]

    return df_empty['dy'].values

def MRIO_mat_to_df(mrio:np.ndarray, products:int, iso3:object=[]):
    # MRIO is 19680 x 19680 matrix, this is 120x164, 120x164   
    # 1. put into dataframe

    # convert to sparse matrix
    mrio = sparse.csc_matrix(mrio.astype('float32')) #type: ignore
    mrio = pd.DataFrame.sparse.from_spmatrix(mrio).reset_index()

    # now we have 
    # columns: index [sec1-reg1 = 0] [sec2-reg1 = 1] ... [sec120 - reg164 = 19680]
    # rows: 1 2 3 ... 19680
    # 2. melt
    mrio = pd.melt(mrio, id_vars=['index']) # type: ignore
    # now it's
    # columns: index[==row-index] variable[==column-index] value
    # rows: 1 2 3 ... 19680
    mrio = mrio[mrio['value']!=0].copy()
    # 3. reindex
    mrio['origin-country'] = (np.floor(mrio['index'] / products)).astype('int16') + 1
    mrio['TRAD_COMM'] = (mrio['index'] % products).astype('int16') + 1
    mrio['target-country'] = (np.floor(mrio['variable'] / products)).astype('int16') + 1
    mrio['PROD_COMM'] = (mrio['variable'] % products).astype('int16') + 1

    if len(iso3) > 0: # type: ignore
        # 4. merge country-iso
        mrio = attach_iso3(mrio, iso3, target=True, origin=True)
    mrio['value'] = mrio['value'].astype('float32')
    mrio = mrio.drop(columns=['index','variable']) # type: ignore
    
    return mrio
