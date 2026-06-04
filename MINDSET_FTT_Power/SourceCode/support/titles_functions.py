# -*- coding: utf-8 -*-
"""
=========================================
titles_functions.py
=========================================
Functions to load classification titles.

Functions included in the file:
    - load_titles
        Load model classifications and titles
"""

# Standard library imports
import os


# Third party imports
from pathlib import Path
import pandas as pd

def load_titles():
    dir_file = os.path.dirname(os.path.realpath(__file__))
    dir_root = Path(dir_file).parents[1]

    titles_path = dir_root / 'Utilities' / 'titles' / 'classification_titles.csv'
    if not titles_path.is_file():
        raise FileNotFoundError(f"Classification titles file not found at: {titles_path}")

    df = pd.read_csv(titles_path, header=None, keep_default_na=False, dtype=str)

    titles_dict = {}
    for _, row in df.iterrows():
        classification = row[0]
        name_type = row[4]
        values = [v for v in row.iloc[5:] if v != '' and pd.notna(v)]
        cleaned = [int(v) if v.isdigit() else v for v in values]
        if name_type == 'Full name':
            titles_dict[classification] = tuple(cleaned)
        elif name_type == 'Short name':
            titles_dict[f"{classification}_short"] = tuple(cleaned)

    # '' (empty string) is used as a placeholder 4th dimension in VariableListing.csv for
    # scalar/unused dims (e.g. BCET has Dim4='').  input_functions.py checks
    # `all(d in known_dims for d in dims[var])` so '' must be a key in titles.
    titles_dict[''] = ('',)

    return titles_dict


def load_converters():
    # Ensure we're using consistent relative paths
    dir_file = os.path.dirname(os.path.realpath(__file__))
    dir_root = Path(dir_file).parents[1] 
   
    
    """ Load model converters. """

    # Declare file name
    conv_file = 'converters.xlsx'

    # Check that classification titles workbook exists
    conv_path = os.path.join(dir_root, 'Utilities', 'titles', conv_file)
    if not os.path.isfile(conv_path):
        print('Converters file not found.')

    conv_dict = pd.read_excel(conv_path, sheet_name = None, index_col = 0)
    conv_dict.pop("Cover")

    # Override T2TI_ERTI with the numbered-name mapping from ftt_t2ti_erti.csv.
    # converters.xlsx uses 12 aggregate T2TI names ('Nuclear', 'Oil', ÔÇª) which diverge
    # from classification_titles.csv's numbered names ('1 Nuclear', '2 Oil', ÔÇª).
    # ftt_t2ti_erti.csv uses the same numbered T2TI/ERTI names as classification_titles.csv.
    erti_path = os.path.join(dir_root, 'Utilities', 'ftt_t2ti_erti.csv')
    if os.path.isfile(erti_path):
        conv_dict['T2TI_ERTI'] = pd.read_csv(erti_path, index_col='T2TI')

    # Return titles dictionary
    return conv_dict