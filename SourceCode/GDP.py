# -*- coding: utf-8 -*-
"""
Created on Tue Aug  1 17:36:45 2023

@author: wb582890
"""

import numpy as np

class GDP():
    
    """
    This class collects the variables and parameters related to GDP and calculates base GVA
    and GVA changes.

    Parameters
    ----------
    A_matrix : class
        Input coefficient matrix.
    price_index : DataFrame
        Price index.
    q_base : DataFrame
        Output base taken from the previous year.
    
    Methods
    -----------
    calc_gva_base
        Re-calculates GVA base based on output base and value added IO coefficientst in the first period of the simulation.
    calc_gva_changes
        Calculates changes in GVA.
    """ 
    
    def __init__(self, A_matrix, price_index, q_base):
        self.A_matrix = A_matrix
        self.q_base = q_base
        self.price_index = price_index
    
    def calc_gva_base(self, type_="constant"):
        I = np.identity(len(self.A_matrix))
        
        if type_ == "constant":
            # Output is multiplied here with Identity matrix - Input coefficients
            # This derives value added coefficients which are then multiplied with
            # gross output
            gva = self.q_base * np.sum(I - self.A_matrix, axis=0)

        elif type_ == "current":
            # get nominal output = q_base * price_index
            # remove nominal value intermediates, which is A_matrix * price_index
            # remaining is nominal gva
            gva = (self.q_base * self.price_index) * np.sum(I - np.divide(np.multiply(self.A_matrix,self.price_index[:, np.newaxis]), self.price_index), axis=0) 
            # gva = (self.q_base * self.price_index) * np.sum(I - self.A_matrix, axis=0)    
        
        return gva
    
    def calc_gva_changes(self, dq, A1, type_="constant"):
        if type(dq) != list:
            I = np.identity(len(self.A_matrix))
            if type_ == "constant":
                dgva = dq * np.sum(I - A1, axis=0)
            elif type_ == "current":
                dgva = dq * np.sum(I - np.divide(np.multiply(A1,self.price_index[:, np.newaxis]), self.price_index), axis=0)
            return dgva
        else:
            dgva = {}
            I = np.identity(len(self.A_matrix))
            
            for i in range(len(dq)):
                if type_ == "constant":
                    dgva_i = dq[i] * np.sum(I - A1, axis=0)
                elif type_ == "current":
                    dgva_i = dq[i] * np.sum(I - np.divide(np.multiply(A1,self.price_index[:, np.newaxis]), self.price_index), axis=0)
                    # dgva_i = dq[i] * np.sum(I - A1, axis=0)
                dgva[i] = dgva_i
            return dgva.values()
    