# -*- coding: utf-8 -*-
"""
Created on Mon Jun  5 14:11:05 2023

@author: wb582890
"""

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import spsolve
import scipy.io
import scipy.linalg
from scipy.optimize import minimize, lsq_linear
import time
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df
from functools import wraps
from datetime import datetime
import os
import warnings
                

io_aggregate_time = dict()

def timing_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        total_time = end_time - start_time

        fname = func.__name__

        cumulative = io_aggregate_time.get(fname, 0)
        io_aggregate_time[fname] = cumulative + total_time

        # if its longer than a minute, print as minutes:seconds format
        if end_time - start_time > 60:
            minutes = int((end_time - start_time) / 60)
            seconds = int((end_time - start_time) % 60)
            # print(f"IO MODULE: {func.__name__} took {minutes}:{seconds} minutes")
        else:
            # print(f"IO MODULE: {func.__name__} took {end_time - start_time:.2f} seconds")
            pass

        return result
    return wrapper

class IO:
    """
    A class used to reconstruct new Input-Output (IO) matrices and calculate 
    output changes from new IO matrix and Final Demand (FD) vectors.

    Attributes
    ----------
    exog_vars : class
        a formatted string to print out what the  says
    name : str
        the name of the 
    sound : str
        X
    num_legs : int
        X

    Methods
    -------
    says(sound=None)
        X
    
    """
    @timing_decorator
    def __init__(self, exog_vars):
        """
        Test

        Parameters
        ----------
        exog_vars : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        """
        self.mrio_id = exog_vars.mrio_id
        self.A_id = exog_vars.A_id
        self.IND_BASE = exog_vars.IND_BASE
        self.IO_PATH = exog_vars.IO_PATH
        self.year = 2019
        self.GLORIAv = exog_vars.GLORIAv

        self.CRITICALITY = exog_vars.GLORIA_CRITICALITY.astype({'Nr_Input':'int16','Nr_Ind':'int16'})\
            .rename(columns={'Nr_Input':'TRAD_COMM','Nr_Ind':'PROD_COMM'})[['PROD_COMM','TRAD_COMM','Criticality']]

        self.HH_BASE = exog_vars.HH_BASE
        self.GOV_BASE = exog_vars.GOV_BASE
        self.FCF_BASE = exog_vars.FCF_BASE
        self.NPISH_BASE = exog_vars.NPISH_BASE
        self.INV_BASE = exog_vars.INV_BASE

        self.P = exog_vars.P
        self.R = exog_vars.R
        self.R_list = exog_vars.R['Region_acronyms'].tolist()
        self.P_list = exog_vars.P['Lfd_Nr'].to_list()

        self.DIMS = len(self.R_list) * len(self.P_list)
        
        try:
            self.Y_BASE = exog_vars.Y_BASE
        except AttributeError:
            pass
        try:
            self.L_BASE = exog_vars.L_BASE
        except AttributeError:
            pass
        try:
            self.G_BASE = exog_vars.G_BASE
        except AttributeError:
            pass

    @timing_decorator
    def io_change(self, io_change_data, sparse_matrix):
        # sparse_matrix structure is 
        # REG_imp	PROD_COMM	REG_exp	TRAD_COMM	IO_coef_trade
        # for now trade shock is implemented on exports

        # io_change_data structure is
        # REG_imp PROD_COMM REG_exp TRAD_COMM Type Value

        # for now ignore type, replace values always
        # keep other values intact

        # ? consolidate io_change_data
        io_change_data_ = io_change_data.groupby(['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','Type']).agg({'Value':'sum'}).reset_index()

        # do impact
        sparse_matrix = sparse_matrix.merge(io_change_data_.astype({'TRAD_COMM':'int','PROD_COMM':'int'}),how='left', on=['REG_exp','TRAD_COMM','REG_imp','PROD_COMM'])
        
        # replace
        sel = (~sparse_matrix['Value'].isna()) & (sparse_matrix['Type']=='replace')
        sparse_matrix.loc[sel,'IO_coef_trade'] = sparse_matrix.loc[sel,'Value']

        # percentage
        sel = (~sparse_matrix['Value'].isna()) & (sparse_matrix['Type']=='rel')
        sparse_matrix.loc[sel,'IO_coef_trade'] = sparse_matrix.loc[sel, 'IO_coef_trade'] * (1 + sparse_matrix.loc[sel, 'Value'])

        # max IO_coef_trade per column
        sparse_matrix['IO_coef_col_total'] = sparse_matrix.groupby(['REG_imp','PROD_COMM'])['IO_coef_trade'].transform('sum')

        mask = sparse_matrix['IO_coef_col_total'] < 0.03
        sparse_matrix.loc[mask, 'IO_coef_trade'] = sparse_matrix.loc[mask, 'IO_coef_trade'] * (0.03/sparse_matrix.loc[mask, 'IO_coef_col_total'])
        mask = sparse_matrix['IO_coef_col_total'] > 0.97
        sparse_matrix.loc[mask, 'IO_coef_trade'] = sparse_matrix.loc[mask, 'IO_coef_trade'] * (0.97/sparse_matrix.loc[mask, 'IO_coef_col_total'])

        sparse_matrix = sparse_matrix.drop(columns=['Value','Type','IO_coef_col_total'])
        sparse_matrix = sparse_matrix.set_index(['REG_imp','PROD_COMM','REG_exp','TRAD_COMM'])

        return sparse_matrix

    @timing_decorator
    def load_L_base(self):
        self.build_A_base()
        self.build_A_matrix()
        if 'L_BASE' in dir(self):
            self.L_BASE = self.L_BASE["L_base"] # type: ignore
        else:
            self.invert_A_base()

    @timing_decorator
    def load_G_base(self):
        if 'G_BASE' in dir(self):
            self.G_BASE = self.G_BASE["G_base"]
        else:
            self.build_B_base()
            self.invert_B_base()

    @timing_decorator
    def build_B_base(self):
        # Compute B or output coefficient matrix
        # this will be used to create the G (Ghosh) matrix or G_base
        # this is a matrix where row totals are 1, row elements are shares of this

        # TO account for criticality we're erasing or reducing those flows for the 
        # B matrix calculation which are not critical
        B_BASE_df = self.IND_BASE.reset_index()
        # B_BASE_df = B_BASE_df.merge(self.CRITICALITY, how='left', on=['PROD_COMM','TRAD_COMM'])
        # B_BASE_df['z_bp'] = B_BASE_df['z_bp'] * B_BASE_df['Criticality']
        B_BASE_df = B_BASE_df[['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','z_bp']].copy()
        B_BASE_df = B_BASE_df.set_index(['REG_imp','PROD_COMM','REG_exp','TRAD_COMM'])

        B_BASE_df = B_BASE_df.unstack(level=["REG_imp","PROD_COMM"])
        B_BASE_df.columns = B_BASE_df.columns.droplevel(0)

        B_temp = pd.DataFrame(
            np.zeros((self.DIMS,self.DIMS)), index=self.A_id, columns=self.A_id)
        B_temp.loc[B_BASE_df.index, B_BASE_df.columns] = B_BASE_df

        B_BASE = B_temp.fillna(0)
        B_BASE = B_BASE.to_numpy()
        
        # actual calculation
        B_BASE = (B_BASE.T/(B_BASE.sum(axis=1)+self.y0)).T
        B_BASE[np.isnan(B_BASE)] = 0

        # if in the diagonal the element is 1.0 then when we subtract from the identity matrix
        # we will get a singular matrix and will not be able to do the inverse
        # not that a 1.0 diagonal element makes too much sense anywa
        # it was particularly bad in Gabon 32-35 sectors
        # so we replace if 1.0 in diagonal with 0.99

        d_ = B_BASE.diagonal().copy()
        d_[d_==1] = 0.99
        np.fill_diagonal(B_BASE, d_)

        # test for determinant anyway
        if np.linalg.slogdet(np.identity(len(B_BASE)) - B_BASE)[1] == -np.inf:
            print("Determinant is zero, cannot proceed")
            exit()
        
        self.B_BASE = B_BASE

    @timing_decorator
    def invert_B_base(self, B_BASE_ext=None):

        if B_BASE_ext is None:
            B_BASE = self.B_BASE
        else:
            B_BASE = B_BASE_ext
        # to get the G (Ghoshian) matrix
        convert_time = time.time()

        I = np.identity(len(B_BASE))

        inverse_time = datetime.now()

        G_BASE = np.linalg.inv(I - B_BASE)

        if B_BASE_ext is None:
            self.G_BASE = G_BASE

            print("G_base inversion: " + str(datetime.now() - inverse_time)[2:7] + " mins")

            scipy.io.savemat(
                os.path.join(self.IO_PATH, "Data", "GLORIA_db", f"GLORIA_G_Base_{str(self.year)}.mat"),
                {"G_base": G_BASE})
            
            print("--- G_base parsing: %s s ---" % round(time.time() - convert_time, 1))
        else:
            return (G_BASE)

    @timing_decorator
    def build_A_matrix(self, input_df=None, variable="a_bp"):
        # compute A matrix / input coefficient matrix
        # goal is to conver a sparse matrix stored in df to a full matrix
        # ! keep in mind that column totals of A does NOT add up to 1.0
        # ! as VA is missing from the A matrix
        # TODO: this will replace both build_A_base and build_A_trade
        if input_df is None:
            input_df = self.IND_BASE

        df_ = input_df.reset_index()
        sel_ = ['REG_imp','REG_exp','TRAD_COMM','PROD_COMM', variable]
        df_ = df_[sel_].astype({variable:'float64'})

        # set dimensions
        def set_dimensions(what, categories):
            df_[what] = df_[what].astype('category')
            df_[what] = df_[what].cat.set_categories(categories, ordered=True)
            return True
        
        set_dimensions('REG_imp',self.R_list)
        set_dimensions('REG_exp',self.R_list)
        set_dimensions('PROD_COMM',self.P_list)
        set_dimensions('TRAD_COMM',self.P_list)

        df_ = df_.pivot_table(index=['REG_imp','PROD_COMM'], columns=['REG_exp','TRAD_COMM'], values=variable, fill_value=0, dropna=False, observed=False)
        # numpy matrix stores values the other way
        df_ = df_.T.values

        return df_

    @timing_decorator
    def build_A_base(self):
        # Compute A or input coefficient matrix
        # this will be used to create the L (Leontief) matrix or L_base
        A_BASE_df = self.IND_BASE.loc[:, ["a_bp"]]
        
        A_BASE_df = A_BASE_df.unstack(level=["REG_imp","PROD_COMM"])
        A_BASE_df.columns = A_BASE_df.columns.droplevel(0)

        A_temp = pd.DataFrame(np.zeros((self.DIMS,self.DIMS)), index=self.A_id, columns=self.A_id)
        A_temp.loc[A_BASE_df.index, A_BASE_df.columns] = A_BASE_df

        A_BASE = A_temp.fillna(0)
        A_BASE = A_BASE.to_numpy()
        
        self.A_BASE = A_BASE

    @timing_decorator
    def build_A_trade(self, ind_trade):

        A1_df = ind_trade.unstack(level=["REG_imp","PROD_COMM"]).astype({'IO_coef_trade':'float64'})
        A1_df.columns = A1_df.columns.droplevel(0)

        A_temp = pd.DataFrame(np.zeros((self.DIMS,self.DIMS), dtype="float64"), index=self.A_id, columns=self.A_id)
        A_temp.loc[A1_df.index, A1_df.columns] = A1_df.values

        A1 = A_temp.fillna(0)
        A1 = A1.to_numpy(dtype="float64")

        return A1
    
    @timing_decorator
    def invert_A_base(self,save=True, A_BASE_ext=None):

        if A_BASE_ext is None:
            A_BASE = self.A_BASE
        else:
            A_BASE = A_BASE_ext
        
        I = np.identity(len(A_BASE))

        # Compute L_base
        L_BASE = np.linalg.inv(I - A_BASE)

        # Save L_base to file
        if A_BASE_ext is None:
            if save:
                scipy.io.savemat(
                    os.path.join(self.IO_PATH, "Data", "GLORIA_db", f"GLORIA_L_Base_{str(self.year)}.mat"),
                    {"L_base": L_BASE})
            self.L_BASE = L_BASE
        else: 
            return(L_BASE)
        
    @timing_decorator
    def calc_Leontieff(self,A_matrix):
        I = np.identity(len(A_matrix))
        L_BASE = np.linalg.inv(I - A_matrix)

        return L_BASE

    @timing_decorator
    def update_Leontieff(self,A_matrix):
        
        I = np.identity(len(A_matrix))
        # Compute L_base
        self.L_BASE = np.linalg.inv(I - A_matrix)

    @timing_decorator
    def load_Y_base(self):
        if 'Y_BASE' in dir(self):
            y0, y_hh0 = self.Y_BASE["y0"], self.Y_BASE["y_hh0"]
            y_gov0, y_fcf0 = self.Y_BASE["y_gov0"], self.Y_BASE["y_fcf0"]
            y_npish, y_inv = self.Y_BASE["y_npish"], self.Y_BASE["y_inv"]

            self.y0, self.y_hh0 = y0[0], y_hh0[0]
            self.y_gov0, self.y_fcf0 = y_gov0[0], y_fcf0[0]
            self.y_npish, self.y_inv = y_npish[0], y_inv[0]

        else:
            y_hh0 = MRIO_df_to_vec(self.HH_BASE.groupby(['REG_exp','TRAD_COMM']).agg({'VIPA':'sum'}).reset_index(), 'REG_exp', 'TRAD_COMM', 'VIPA', self.R_list,  self.P_list)
            y_gov0 = MRIO_df_to_vec(self.GOV_BASE.groupby(['REG_exp','TRAD_COMM']).agg({'VIGA':'sum'}).reset_index(), 'REG_exp', 'TRAD_COMM', 'VIGA', self.R_list,  self.P_list)
            y_fcf0 = MRIO_df_to_vec(self.FCF_BASE.groupby(['REG_exp','TRAD_COMM']).agg({'VDFA':'sum'}).reset_index(), 'REG_exp', 'TRAD_COMM', 'VDFA', self.R_list,  self.P_list)
            y_inv = MRIO_df_to_vec(self.INV_BASE.groupby(['REG_exp','TRAD_COMM']).agg({'INV':'sum'}).reset_index(), 'REG_exp', 'TRAD_COMM', 'INV', self.R_list,  self.P_list)
            y_npish = MRIO_df_to_vec(self.NPISH_BASE.groupby(['REG_exp','TRAD_COMM']).agg({'NPISH':'sum'}).reset_index(), 'REG_exp', 'TRAD_COMM', 'NPISH', self.R_list,  self.P_list)

            y0 = y_hh0 + y_gov0 + y_fcf0 + y_npish + y_inv

            # Save Y_base to file
            # scipy.io.savemat(
            #     self.IO_PATH + f"GLORIA_db\\{self.GLORIAv}\\{str(self.year)}\\GLORIA_Y_Base_{str(self.year)}.mat",
            #     {"y0": y0, "y_hh0": y_hh0, "y_npish": y_npish,
            #      "y_gov0": y_gov0, "y_fcf0": y_fcf0, "y_inv": y_inv})

            self.y0, self.y_hh0 = y0, y_hh0
            self.y_gov0, self.y_fcf0 = y_gov0, y_fcf0
            self.y_npish, self.y_inv = y_npish, y_inv
    
    @timing_decorator
    def calc_init_q(self):
        # Calculate baseline output
        self.q_base_curr = np.dot(self.L_BASE, self.y0)

        # Calculate output due to household consumption
        self.q_hh = np.dot(self.L_BASE, self.y_hh0)

        # Calculate output due to non-profit institution
        self.q_npish = np.dot(self.L_BASE, self.y_npish)

        # Calculate output due to government final demand
        self.q_gov = np.dot(self.L_BASE, self.y_gov0)

        # Calculate output due to capital formation
        self.q_fcf = np.dot(self.L_BASE, self.y_fcf0)

        # Calculate due to inventory
        self.q_inv = np.dot(self.L_BASE, self.y_inv)
        
    @timing_decorator
    def initialize(self, q_base=None):
        self.load_Y_base()
        self.load_L_base()
        self.load_G_base()
        self.calc_init_q()

        if q_base is not None:
            self.q_base = q_base
        else:
            self.q_base = self.q_base_curr

    @timing_decorator
    def build_dL_ener(self, tax_index, tax_matrix, sec_matrix):
        # Calculate dL0_1
        dL0_1 = np.linalg.inv(
            np.identity(len(tax_index)) - np.dot(
                np.dot(sec_matrix, self.L_BASE), tax_matrix))

        # Calculate dL0_2
        dL0_2 = np.dot(self.L_BASE, np.dot(tax_matrix, dL0_1))

        # Calculate dL0_3
        dL0_3 = np.dot(dL0_2, np.dot(sec_matrix, self.L_BASE))
        
        return dL0_3
    
    @timing_decorator
    def calc_dq_energy(self, dL_ener):
        # Calculate total output as a result of energy elasticities
        self.dq_energy = np.dot(dL_ener, self.y0)

        return self.dq_energy
    
    @timing_decorator
    def build_dy_hh(self, HH_price_effect, variable_):
        # Household demand change due to price changes
        y = pd.DataFrame(self.A_id)
        y["EXP_SEC"] = list(zip(y[0], y[1]))
        y = pd.DataFrame(y.loc[:,"EXP_SEC"])
        
        HH_price_effect = HH_price_effect.reset_index(drop=False)

        dy_hh = HH_price_effect.loc[:,["REG_exp","TRAD_COMM","REG_imp",variable_]]
        dy_hh["EXP_SEC"] = list(zip(dy_hh["REG_exp"], dy_hh["TRAD_COMM"]))
        dy_hh = dy_hh.loc[:,["EXP_SEC","REG_imp",variable_]]
        dy_hh = dy_hh.pivot(index="EXP_SEC", columns="REG_imp",
                            values=variable_)
        dy_hh = y.merge(dy_hh, how="left", on=["EXP_SEC"])
        dy_hh = pd.concat([y, dy_hh.sum(numeric_only=True,axis=1)], axis=1)
        
        self.dy_hh = dy_hh.iloc[:,1].to_numpy()
        
        return self.dy_hh
    
    @timing_decorator
    def build_dy_gov_recyc(self, GOV_recyc):
        # y = pd.DataFrame(self.A_id)
        # y["EXP_SEC"] = list(zip(y[0], y[1]))
        # y = pd.DataFrame(y.loc[:,"EXP_SEC"])

        # GOV_recyc = GOV_recyc.reset_index(drop=False)

        # dy_gov = GOV_recyc.loc[:,["REG_exp","TRAD_COMM","REG_imp","delta_y_gov"]]
        # dy_gov["EXP_SEC"] = list(zip(dy_gov["REG_exp"], dy_gov["TRAD_COMM"]))
        # dy_gov = dy_gov.loc[:,["EXP_SEC","REG_imp","delta_y_gov"]]
        # dy_gov = dy_gov.pivot(index="EXP_SEC", columns="REG_imp", values="delta_y_gov")
        # dy_gov = y.merge(dy_gov, how="left", on=["EXP_SEC"])
        # dy_gov = pd.concat([y, dy_gov.fillna(0).sum(numeric_only=True,axis=1)], axis=1)
        
        # self.dy_gov = dy_gov.iloc[:,1].to_numpy()
        
        return self.dy_gov
    
    @timing_decorator
    def q_iterate(self, A_matrix, q_est, y, tol=10e1, steps=200):
        q_iter1 = q_est.copy()
        # output == interm + final
        q_iter2 = np.dot(A_matrix, q_iter1) + y
        
        i = 0
        
        while np.sum(
                np.divide(abs(q_iter2 - q_iter1), q_iter1,
                          out=np.zeros_like(q_iter1),
                          where=q_iter1!=0)) >= tol and i <= steps:
            q_iter1 = q_iter2.copy()
            q_iter2 = np.dot(A_matrix, q_iter1) + y
            i += 1
        
        if i >= steps:
            print("Iteration does not converge after %s steps" % steps)
        # else: # Turn on when debugging
        #     print("Iteration passes")
        
        return q_iter2

    @timing_decorator
    def calc_dq_energy_subst(self, A_energy):
        # L_new = self.calc_Leontieff(A_energy)
        dq_impact = np.dot(self.L_BASE, self.y0) - self.q_base_curr
        return dq_impact

    # def calc_dq_IO(self, trade_dy):
    #     # calculate value with old Leontieff and with new
    #     # q_base is basically the old result --> y0 x L0 = q_base
    #     # q_final is the new --> y0 x L1 = q_final

    #     q_final = np.dot(self.L_BASE, (self.y0 + trade_dy))
    #     self.dq_IO_eff = q_final - self.q_base_curr

    #     return self.dq_IO_eff
    
    @timing_decorator
    def calc_dq_trade(self, dq_prev):
        dq_impact = np.dot(self.L_BASE, self.y0) - self.q_base_curr - dq_prev

        return dq_impact

    @timing_decorator
    def calc_dq_io(self, q_compare, fd_vec):
        dq_impact = (np.dot(self.L_BASE, fd_vec) - q_compare)

        return dq_impact

    @timing_decorator
    def calc_dq_exog(self, dy):
        dq_exog_fd = np.dot(self.L_BASE, dy)
        
        return dq_exog_fd

        # q_hh = y_hh0 x Leontief

        # dq_hh_price = dy_hh_price x Leontief_new
        # dq_hh_inc = dy_inc_price x Leontief_new
        # ---> dq_hh_trade = y_hh0 x Leontief_new - y_hh0 x Leontief

    # TODO get rid of this and replace with calc_dq_exog
    @timing_decorator
    def calc_dq_hh(self, dy_hh_price, dy_hh_inc, dy_hh_save):

        self.q_hh_IO = np.dot(self.L_BASE, self.y_hh0)
        
        dq_hh_price = np.dot(self.L_BASE, self.y_hh0 + dy_hh_price)
        dq_hh_price -= self.q_hh_IO
        
        self.dq_hh_price = dq_hh_price
        
        dq_hh_inc = np.dot(self.L_BASE, self.y_hh0 + dy_hh_inc)
        dq_hh_inc -= self.q_hh_IO
        
        self.dq_hh_inc = dq_hh_inc

        dq_hh_save = np.dot(self.L_BASE, self.y_hh0 + dy_hh_save)
        dq_hh_save -= self.q_hh_IO
        
        self.dq_hh_save = dq_hh_save
        
        return self.dq_hh_price, self.dq_hh_inc, self.dq_hh_save
    
    # TODO get rid of this and replace with calc_dq_exog
    @timing_decorator
    def calc_dq_gov(self, dy_gov_recyc):
        self.q_gov_IO = np.dot(self.L_BASE, self.y_gov0)
        
        dq_gov_recyc = np.dot(self.L_BASE, self.y_gov0 + dy_gov_recyc)
        dq_gov_recyc -= self.q_gov_IO
        
        self.dq_gov_recyc = dq_gov_recyc
        
        return self.dq_gov_recyc
    
    @timing_decorator
    def calc_dq_inv(self, dy_inv_induced, dy_inv_recyc, dy_inv_exog):
        # ! added investment, recycling, induced, exog should NOT decrease output in 
        # ! other areas therefore this needs to be revised 
        # ! BKD revision as of 5/3/2024

        # INDUCED
        # initial GFCF induced Q
        dq_inv_induced = np.dot(self.L_BASE, dy_inv_induced)
        self.dq_inv_induced = dq_inv_induced
        
        # RECYCLED from govt
        if sum(dy_inv_recyc) != 0:
            dq_inv_recyc = np.dot(self.L_BASE, dy_inv_recyc)
            self.dq_inv_recyc = dq_inv_recyc
        else:
            self.dq_inv_recyc = np.zeros(dq_inv_induced.shape)
            
        # EXOG added
        if sum(dy_inv_exog) != 0:
            dq_inv_exog = np.dot(self.L_BASE, dy_inv_exog)
            self.dq_inv_exog = dq_inv_exog
        else:
            self.dq_inv_exog = np.zeros(dq_inv_induced.shape)
        
        return self.dq_inv_induced, self.dq_inv_recyc, self.dq_inv_exog
    
    @timing_decorator
    def calc_fd_vec(self, q_target, y0=None):

        if not (y0 is None):
            scale = np.max(np.abs(q_target))
            q_scaled = q_target / scale

            y0_scaled = y0 / scale
            lower_bounds = [x*-0.6 if x > 0 else 0 for x in y0_scaled]
            upper_bounds = np.zeros(self.L_BASE.shape[1])
            upper_bounds[:] = np.inf

            min_ = lsq_linear(self.L_BASE, q_scaled, bounds=(lower_bounds, upper_bounds), method='trf', verbose=1)
            x_ = min_.x
            q_x = np.dot(self.L_BASE, x_)

            # get a vector of issues
            diff_q = q_scaled - q_x
            diff = np.nan_to_num(q_x / q_scaled, nan=0, posinf=0, neginf=0)
            diff[diff >= 0] = 0.0

            diff_q[diff == 0.0] = 0.0

            min2_ = lsq_linear(self.L_BASE, diff_q, bounds=(lower_bounds, upper_bounds), method='trf', verbose=1)

            x_final = x_ + min2_.x

            # if not min_.success:
            #     print("######################################################################################")
            #     print("!!!! ERROR: Optimization for calibration did not work.")
            #     print("######################################################################################")
            #     import pdb; pdb.set_trace()
            #     warnings.warn(f"Optimization did not converge: {min_.message}", RuntimeWarning)

            # calculate demand vector that leads to q_target
            fd_vector = x_final * scale    
        else:
            fd_vector = np.linalg.solve(self.L_BASE, q_target)

        return fd_vector
    
    @timing_decorator
    def calc_dq_supply_constraint2(self, dq_impact, dq_total):
        # we limit production in certain industries, because of labour supply constraints
        # these limits, however, limit growth in other industries
        # however, if there are simultaneous effects we don't want to shut-down certain parts "double"
        # ! the thing is if there are multiple impacts from different sectors, we want to keep the minimum
        # ! but we don't want to duplicate the effects, so we need to iterate on dq_impact

        # only consider negative dq
        dq_impact[dq_impact > 0.0] = 0.0

        # dq_impact_in = None
        # for i in range(0, len(dq_impact)):
        #     dq_impact_ = np.zeros(len(dq_impact))
        #     dq_impact_[i] = dq_impact[i]
        #     if dq_impact_in is None:
        #         dq_impact_in = dq_impact_
        #     else:
        #         dq_impact_in = np.vstack([dq_impact_in, dq_impact_])

        dq_impact_in = np.diag(dq_impact)

        # dq_impact_out = None
        # for i in range(0,len(dq_impact)):
        #     dq_impact_out_ = np.dot(self.G_BASE, dq_impact_in[i])
        #     if dq_impact_out is None:
        #         dq_impact_out = dq_impact_out_
        #     else:
        #         dq_impact_out = np.vstack([dq_impact_out, dq_impact_out_])

        dq_impact_out = dq_impact_in @ self.G_BASE.T

        dq_impact = dq_impact_out.min(axis=0)
        del dq_impact_in, dq_impact_out

        # can only crub growth, not baseline
        # ! we only need to consider if dq_total is positive
        dq_impact[dq_total <= 0.0] = 0.0
        dq_impact[((dq_impact * -1) > dq_total) & (dq_total > 0.0)] = dq_total[((dq_impact * -1) > dq_total) & (dq_total > 0.0)] * -0.90

        fd_share = self.y0 / self.q_base
        dy_impact = fd_share * dq_impact

        return {'dq': dq_impact,
                'dy': dy_impact}

    @timing_decorator
    def calc_dq_supply_constraint(self, supply_constraint, q_base=None):
        # supply_constraint
        # REG_imp PROD_COMM Value Type
        # TODO: non-percent type

        if q_base is None:
            q_base = self.q_base

        sc_ = supply_constraint[supply_constraint['Type'].str.contains("rel")].copy()
        sc_ = sc_[sc_['Value'] != 0].copy()
        sc_ = sc_.astype({'PROD_COMM':'int16'})

        if len(sc_) > 0:
            sc_['id'] = list(zip(sc_['REG_imp'],sc_['PROD_COMM']))
            sc_ = sc_.set_index('id')

            sc_temp = pd.DataFrame(np.zeros((self.DIMS,1)), index=self.A_id, columns=['Value'])
            sc_temp.loc[sc_.index, 'Value'] = sc_['Value'].values
            
            sc_temp = sc_temp.fillna(0)['Value'].to_numpy()

            # ! only negative impacts
            sc_temp[sc_temp > 0] = 0

            dq_impact = (q_base) * sc_temp
            dq_impact_direct = dq_impact.copy()

            # 19680 array of supply constraint modifiers
            # now let's iterate conditional on the new q_max

            # ! the thing is if there are multiple impacts from different sectors, we want to keep the minimum
            # ! but we don't want to duplicate the effects, so we need to iterate on dq_impact

            dq_impact_in = None
            for i in range(0, len(dq_impact)):
                dq_impact_ = np.zeros(len(dq_impact))
                dq_impact_[i] = dq_impact[i]
                if dq_impact_in is None:
                    dq_impact_in = dq_impact_
                else:
                    dq_impact_in = np.vstack([dq_impact_in, dq_impact_])

            dq_impact_out = None
            for i in range(0,len(dq_impact)):
                dq_impact_out_ = np.dot(self.G_BASE.T, dq_impact_in[i])
                if dq_impact_out is None:
                    dq_impact_out = dq_impact_out_
                else:
                    dq_impact_out = np.vstack([dq_impact_out, dq_impact_out_])
                    
            idx = np.abs(dq_impact_out).argmax(axis=0)
            dq_impact = dq_impact_out[idx, np.arange(dq_impact_out.shape[1])]
            
            del dq_impact_in, dq_impact_out

            # should not go beyond 100%
            dq_impact[(dq_impact * -1) > q_base] = q_base[(dq_impact * -1) > q_base] * -0.90

        else:
            dq_impact = np.zeros(len(q_base))
            dq_impact_direct = dq_impact.copy()

        result = {'dq_supply_constraint': dq_impact,
                  'dq_supply_constraint_direct': dq_impact_direct,
                  'dy_supply_constraint': self.calc_fd_vec(dq_impact)}
        
        self.dq_supply_constraint = dq_impact
        
        return result
    
    #! this one is with upstream effects, so VA impacts are distributed across
    @timing_decorator
    def calc_dq_supply_constraint3(self, supply_constraint, q_base=None):
        # supply_constraint
        # REG_imp PROD_COMM Value Type
        # TODO: non-percent type

        if q_base is None:
            q_base = self.q_base

        sc_ = supply_constraint[supply_constraint['Type'].str.contains("rel")].copy()
        sc_ = sc_[sc_['Value'] != 0].copy()
        sc_ = sc_.astype({'PROD_COMM':'int16'})

        if len(sc_) > 0:
            sc_['id'] = list(zip(sc_['REG_imp'],sc_['PROD_COMM']))
            sc_ = sc_.set_index('id')

            sc_temp = pd.DataFrame(np.zeros((self.DIMS,1)), index=self.A_id, columns=['Value'])
            sc_temp.loc[sc_.index, 'Value'] = sc_['Value'].values
            
            sc_temp = sc_temp.fillna(0)['Value'].to_numpy()

            # ! only negative impacts
            sc_temp[sc_temp > 0] = 0

            dq_impact = (q_base) * sc_temp
            dq_impact_direct = dq_impact.copy()

            # 19680 array of supply constraint modifiers
            # now let's iterate conditional on the new q_max

            # ! the thing is if there are multiple impacts from different sectors, we want to keep the minimum
            # ! but we don't want to duplicate the effects, so we need to iterate on dq_impact

            dq_impact_in = None
            for i in range(0, len(dq_impact)):
                dq_impact_ = np.zeros(len(dq_impact))
                dq_impact_[i] = dq_impact[i]
                if dq_impact_in is None:
                    dq_impact_in = dq_impact_
                else:
                    dq_impact_in = np.vstack([dq_impact_in, dq_impact_])

            dq_impact_out = None
            for i in range(0,len(dq_impact)):
                dq_impact_out_ = np.dot(self.G_BASE.T, dq_impact_in[i])
                if dq_impact_out is None:
                    dq_impact_out = dq_impact_out_
                else:
                    dq_impact_out = np.vstack([dq_impact_out, dq_impact_out_])
            #! add upstream here
            for i in range(0, len(dq_impact)):
                dq_impact_out_ = np.dot(self.L_BASE, dq_impact_in[i])
                dq_impact_out = np.vstack([dq_impact_out, dq_impact_out_])
                    
            idx = np.abs(dq_impact_out).argmax(axis=0)
            dq_impact = dq_impact_out[idx, np.arange(dq_impact_out.shape[1])]
            
            # dq_impact = dq_impact_out.sum(axis=0)
            
            del dq_impact_in, dq_impact_out

            # should not go beyond 100%
            dq_impact[(dq_impact * -1) > q_base] = q_base[(dq_impact * -1) > q_base] * -0.90

        else:
            dq_impact = np.zeros(len(q_base))
            dq_impact_direct = dq_impact.copy()

        result = {'dq_supply_constraint': dq_impact,
                  'dq_supply_constraint_direct': dq_impact_direct,
                  'dy_supply_constraint': self.calc_fd_vec(dq_impact)}
        
        self.dq_supply_constraint = dq_impact
        
        return result

    @timing_decorator
    def calc_fd_impact(self, fd_vec):

        fd_df = MRIO_vec_to_df(fd_vec, 'residualFD', len(self.P), self.R)\
        .rename(columns={'target-country-iso3':'REG_exp','target-sector':'TRAD_COMM'}).drop(columns=['target-country'])

        hh_cons = self.HH_BASE.reset_index() # VIPA
        fcf_cons = self.FCF_BASE.reset_index() # VDFA
        gov_cons = self.GOV_BASE.reset_index() # VIGA

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

        fd_df = fd_df.drop(columns=['VIPA','VIGA','VDFA']).rename(columns={'VIGA_new':'VIGA','VIPA_new':'VIPA','VDFA_new':'VDFA'})

        return fd_df


