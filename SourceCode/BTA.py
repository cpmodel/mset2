# -*- coding: utf-8 -*-
"""
Created on Thu Jun 29 16:44:06 2023

@author: wb582890
"""

import numpy as np
import pandas as pd
from concurrent import futures
from SourceCode.utils import resolve_hyphen, resolve_comma, resolve_all
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df

class BTA:
    """
    This class collects the variables and parameters related to border trade adjustment and calculates CBAM incidence.

    Parameters
    ----------
    scenario : class
        Class for scenario assumptions.
    bta : int
        BTA counter.
    regions : list
        List of regions.
    temp : str
        Path to temporary file.
    exog_vars : class
        Class for exogenous variables.
    
    Methods
    -----------
    cbam_incidence_loop
        Re-calculates GVA base based on output base and value added IO coefficientst in the first period of the simulation.
    calc_cbam_incidence
        Calculates changes in GVA.
    """ 
    
    def __init__(self, scenario, bta, regions, temp, exog_vars):
        self.bta = bta
        self.REGIONS = regions
        self.REGIONS_list = exog_vars.COU_ID
        self.scenario_file = scenario.scenario_file
        self.ALL_POLLUTANTS = exog_vars.ALL_POLLUTANTS
        self.ALL_PROCESS_EMISSIONS = exog_vars.ALL_PROCESS_EMISSIONS
        self.temp = temp
        self.YEAR = scenario.YEAR

        try:
            self.carbon_tax_countries = scenario.carbon_tax_countries
        except AttributeError:
            pass

        try:
            cbam_setup = pd.read_excel(self.scenario_file, sheet_name="CBAM", skiprows=14)
            cbam_setup = cbam_setup[['Importing country*','Exporting country*','Sector covered*', self.YEAR]]
        except ValueError:
            # catch if there is no sheet
            cbam_setup = pd.DataFrame(columns=['REG_imp','TRAD_COMM','REG_exp',self.YEAR])
        cbam_setup.columns = ['REG_imp','REG_exp','TRAD_COMM','cbam']

         # ! CBAM is switch; 1 = turn on, 0 turn off
        # REG_exp with exclusion
        sel = cbam_setup['REG_exp'].str.contains(r"ALL\[")
        exclude = cbam_setup[sel].copy()
        exclude['REG_exp_excl'] = exclude['REG_exp'].str.extract(r"^ALL\[(.*?)\]")[0].str.split(",")
        cbam_setup.loc[sel,'REG_exp'] = 'ALL'

        # resolve keys
        cbam_setup = resolve_comma(cbam_setup, 'TRAD_COMM') #type:ignore
        cbam_setup = resolve_hyphen(cbam_setup, 'TRAD_COMM')
        cbam_setup = resolve_all(cbam_setup, 'TRAD_COMM', [x for x in np.arange(1,121)])


        cbam_setup = resolve_comma(cbam_setup, 'REG_imp')
        cbam_setup = resolve_comma(cbam_setup, 'REG_exp')
        cbam_setup = resolve_all(cbam_setup, 'REG_imp', self.REGIONS['Region_acronyms'].to_list())
        cbam_setup = resolve_all(cbam_setup, 'REG_exp', self.REGIONS['Region_acronyms'].to_list())

        for k, r in exclude.iterrows():
            cbam_setup = cbam_setup[((cbam_setup['REG_imp']!=r['REG_imp'])|\
                                     (cbam_setup['TRAD_COMM']!=r['TRAD_COMM']))|\
                                        (~cbam_setup['REG_exp'].isin(r['REG_exp_excl']))]

        # * cbam setup structure
        # * REG_exp REG_imp TRAD_COMM cbam
        bta_imp = cbam_setup

        self.emission_matrix = None
        self.scope1 = None
        self.scope2 = None
        
        self.bta_imp = bta_imp

    def cbam_incidence_loop(self, country):
        """
        This loop calculates the CBAM incidence given carbon_tax_rate files generated
        by earlier functions (these are stored in the Temp folder).
        This loop is only expected to be run within the `calculate_cbam_incidence` function
        in a parallel loop.
        """

        # first get the carbon_tax_rate of the target
        carbon_tax_rate = self.temp.read_from_pickle("carbon_tax_rate", delete_=False)
        # calculate emission cost per flow
        carbon_tax_rate = carbon_tax_rate.pipe(lambda d: d[~d['ctax'].isna()])
        carbon_tax_rate = carbon_tax_rate.astype({'PROD_COMM':'str'})
        carbon_tax_rate = carbon_tax_rate.drop(columns=['REG_exp','TRAD_COMM'])
        # reg_exp and trad_comm is just technicality
        carbon_tax_rate = carbon_tax_rate.groupby(['PROD_COMM','REG_imp']).agg({'ctax':'mean'}).reset_index()
        # PROD_COMM REG_imp ctax

        mrio = self.emission_matrix[self.emission_matrix['REG_imp']==country]
        # share of flow within REG_imp / target-sector
        mrio = mrio.astype({'PROD_COMM': 'str', 'TRAD_COMM': 'str'})        
        # mrio = mrio.groupby(['REG_imp','REG_exp','TRAD_COMM']).agg({'z_bp':'sum','imp_exp_TRAD_share':'sum'}).reset_index()

        cbam_incidence = mrio.merge(self.scope1, how='left', on=['REG_exp','TRAD_COMM'])\
                                     .merge(self.scope2, how='left', on=['REG_exp','TRAD_COMM'])

        cbam_incidence['scope1_ktco2'] = cbam_incidence['scope1_ktco2'] * cbam_incidence['imp_exp_TRAD_share']
        cbam_incidence['scope2_ktco2'] = cbam_incidence['scope2_ktco2'] * cbam_incidence['imp_exp_TRAD_share']
        
        # with SCOPE1 and SCOPE2 merged on REG_exp and TRAD_COMM
        # scope1 ans scope2 values are duplicated across REG_IMP; but there is only one REG_imp
        
        # carbon_tax_rate -> reg_exp and TRAD_COMM is only technical | we're within a single reg-imp
        # ! TODO carbon_tax_rate technically has REG_exp and TRAD_comm, but it shouldnt
        cbam_incidence = cbam_incidence.merge(carbon_tax_rate.rename(columns={'PROD_COMM':'TRAD_COMM','ctax':'exp_ctax','REG_imp':'REG_exp'}),                                        
                                               how='left',on=['TRAD_COMM','REG_exp'])\
                                                .merge(carbon_tax_rate.rename(columns={'PROD_COMM':'TRAD_COMM','ctax':'imp_ctax'}),                                        
                                               how='left',on=['TRAD_COMM','REG_imp']).fillna(0)
        
        # actual calculations
        # ! DEFAULT values are need to be added for missing emission rates

        # self.bta_imp stores the CBAM switches
        # 'REG_imp','TRAD_COMM','REG_exp','cbam'

        cbam_incidence = cbam_incidence.merge(self.bta_imp.astype({'TRAD_COMM': 'str'}),
                                               how='left', on=['REG_imp','TRAD_COMM','REG_exp'])

        
        cbam_incidence['cbam_cost'] =\
              (cbam_incidence['scope1_ktco2'] + cbam_incidence['scope2_ktco2']) * (cbam_incidence['imp_ctax'] - cbam_incidence['exp_ctax'])
        cbam_incidence.loc[cbam_incidence['exp_ctax'] > cbam_incidence['imp_ctax'], 'cbam_cost'] = 0.0
        
        cbam_incidence['cbam_cost'] = cbam_incidence['cbam_cost'] * cbam_incidence['cbam']
         # SCOPE1 and SCOPE2 EMISSIONS in tCO2, ctax in USD/tCO2
        cbam_incidence = cbam_incidence[~cbam_incidence['cbam_cost'].isna()]

        # calculate base monetary value of flow to get tax incidence in %
        # merge to emission cost
        
        return cbam_incidence[['REG_imp','REG_exp','PROD_COMM','TRAD_COMM','cbam_cost']].copy()

    def calc_cbam_incidence(self, mrio, carbon_content, hh, fcf, gov):
        # carbon content is #
        # ['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','EF_ktCO2_per_kUSD']

        # do for countries with carbon tax
        carbon_tax_countries = self.carbon_tax_countries
        if len(carbon_tax_countries) == 0:
            return pd.DataFrame(columns=['REG_imp','REG_exp','PROD_COMM','TRAD_COMM','cbam_cost'])
        cbam_incidence_all = None

        mrio = mrio.reset_index()

        try:
            mrio = mrio[['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','z_bp']].copy()
        except KeyError:
            # import pdb; pdb.set_trace()
            mrio = mrio[['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','z_bp_ener']].copy()
            mrio = mrio.rename(columns={'z_bp_ener':'z_bp'})
        mrio = mrio.astype({'PROD_COMM':'str','TRAD_COMM':'int'})

        # bring in FD 
        hh_base = hh.reset_index().rename(columns={'VIPA':'z_bp'}).assign(PROD_COMM = "FD_1")
        fcf_base = fcf.reset_index().rename(columns={'VDFA':'z_bp'}).assign(PROD_COMM = "FD_4")
        gov_base = gov.reset_index().rename(columns={'VIGA':'z_bp'}).assign(PROD_COMM = "FD_3")

        mrio = pd.concat([mrio, hh_base, fcf_base, gov_base])
        self.emission_matrix = mrio

        self.emission_matrix['imp_exp_TRAD_share'] = self.emission_matrix['z_bp'] / self.emission_matrix.groupby(['REG_exp','TRAD_COMM'])['z_bp'].transform('sum')
        # REG_imp REG_exp PROD_COMM TRAD_COMM z_bp

        self.emission_matrix = self.emission_matrix.merge(carbon_content, how='left', on=['REG_imp','PROD_COMM','REG_exp','TRAD_COMM'])
        # REG_imp REG_exp PROD_COMM TRAD_COMM z_bp EF_ktCO2_per_kUSD
        self.emission_matrix['emission_ktco2'] = self.emission_matrix['EF_ktCO2_per_kUSD'] * self.emission_matrix['z_bp']

        # # calculate process emissions
        # # target-sector	target-country-iso3	Y_2019	output_kUSD	EF_ktCO2_per_kUSD
        # process_emissions = self.ALL_PROCESS_EMISSIONS[['target-sector','target-country-iso3','EF_ktCO2_per_kUSD']].copy()
        # process_emissions['target-sector'] = process_emissions['target-sector'].astype(str)
        
        # # * TARGET AND ORIGIN is twisted here, bc process emissions are applied not on the incoming, but on the outgoing flow
        # process_emissions = process_emissions.rename(columns={'target-sector':'PROD_COMM','target-country-iso3':'REG_imp'})
        # process_emissions = process_emissions.merge(mrio, how='left', on=['REG_imp','PROD_COMM'])
        # # kUSD * ktco2/kUSD -> ktco2 * 1000
        # # PROCESS EMISSION REG_exp TRAD_COMM REG_imp PROD_COMM
        # process_emissions['PROCESS_EMISSION'] = process_emissions['z_bp'] * process_emissions['EF_ktCO2_per_kUSD'] * 1000
        # process_emissions = process_emissions[['REG_imp','PROD_COMM','REG_exp','TRAD_COMM','PROCESS_EMISSION']]

        # ? calc SCOPE2
        scope2 = self.emission_matrix.query("PROD_COMM == '93'").groupby(['REG_imp']).agg({'emission_ktco2':'sum'}).reset_index()
        scope2 = scope2.rename(columns={'REG_imp':'REG_exp'})
        # ['REG_exp','emission_ktco2'] <- electricity generation emissions by country
       
        electricity_share = self.emission_matrix.query("TRAD_COMM == 93").drop(columns=['TRAD_COMM'])
        electricity_share['share'] = electricity_share['z_bp'] / electricity_share.groupby(['REG_exp'])['z_bp'].transform('sum')
        electricity_share = electricity_share[['REG_exp','REG_imp','PROD_COMM','share']].copy()
        # ['REG_exp','REG_imp','PROD_COMM','share'] <- electricity use shares by producer

        scope2 = electricity_share.merge(scope2, how='left', on=['REG_exp'])
        scope2['scope2_ktco2'] = scope2['emission_ktco2'] * scope2['share']

        scope2 = scope2.groupby(['REG_imp','PROD_COMM']).agg({'scope2_ktco2':'sum'}).reset_index()
        scope2 = scope2.rename(columns={'REG_imp':'REG_exp','PROD_COMM':'TRAD_COMM'})

        # ? calc SCOPE1
        scope1 = self.emission_matrix.groupby(['REG_imp','PROD_COMM']).agg({'emission_ktco2':'sum'}).reset_index()
        # embedded carbon REG_imp \ PROD_COMM
        scope1 = scope1.rename(columns={'REG_imp':'REG_exp','PROD_COMM':'TRAD_COMM','emission_ktco2':'scope1_ktco2'})

        self.scope1 = scope1
        self.scope2 = scope2

        print("Calculating CBAM incidence... Parallel started.")
        futures_ = [] 
        with futures.ThreadPoolExecutor() as executor:
            for c in carbon_tax_countries:
                futures_.append(executor.submit(self.cbam_incidence_loop, c))
        
            tmp_df = []
            # with tqdm(total=len(futures_)) as progress:
            for f in futures.as_completed(futures_):
                    # progress.update()
                tmp_df.append(f.result())
            cbam_incidence_all = pd.concat(tmp_df)

        cbam_incidence_all = cbam_incidence_all[['REG_imp','REG_exp','PROD_COMM','TRAD_COMM','cbam_cost']].copy()
        self.temp.write_to_csv(cbam_incidence_all, 'cbam_incidence_all')

        return cbam_incidence_all