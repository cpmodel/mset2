# MINDSET Dyanmic Macroeconomic Model

## Overview
MINDSET is a global, demand-driven,recursively dynamic macroeconometric simulation model that is used to evaluate how climate change, climate policies, and other development and trade policies affect macroeconomic, sectoral, and labor market outcomes. 
MINDSET stands for Model of Innovation in Dynamic Low-Carbon Structural Economic and Employment Transformations.

## Key Features
- Scenario engine for broad range of fiscal, price-based, and regulatory policies  
- High level of disaggregation, covering 163 regions, with 120 sectors in each regionns  
- Outputs include standard macroeconomic indicators, sectoral employment, greenhouse gas (GHG) emission levels, and prices
- Reproducible data pipeline

## Model Structure

At its core, MINDSET integrates a multi-regional input–output (MRIO) framework with a set of macro-econometric equations that capture
key components, including income, wages, investment, government activity, trade, and energy use. This hybrid
structure enables the model to simulate direct, indirect, and induced effects of shocks and policies across sectors and
regions. The model ensures macroeconomic consistency through accounting identities that reconcile output, income, and expenditure, 
as well as taxes and external balances.

Stocks and lagged variables carry values between years, giving the model strong path dependency. The model begins with the
specification of policy instruments and exogenous drivers, including changes in taxes, government spending, external
demand and prices, interest rates, technological trends, and demographic shifts. These inputs shape the formation of
final demand, which includes household consumption, government expenditure, investment, and exports. Investment
determines capital accumulation and capacity for future production. Imports are determined based on domestic
demand and relative prices.

Final demand then propagates through the MRIO framework, which translates it into sectoral gross output and
intermediate input requirements. This propagation captures both direct and indirect effects across industries and
regions. Given the resulting output levels, the model determines employment, wages, unit labor costs, capacity
utilization, and normal (expected) output. Prices are formed based on costs - including wages, intermediate inputs,
and taxes - as well as margins and import prices. Profits are calculated as the residual between prices and costs.
Incomes accrue to households, firms, and the government, and the model ensures that all accounts are balanced.
Energy demand and emissions are computed based on sectoral output and technology assumptions. At the end of
each period, stocks such as capital and labor force are updated, along with lagged variables and policy paths, setting
the stage for the next period.

### Core Modules
- **Scenario**: variables and parameters related to policy scenario assumptions  
- **Calibration**: fitting to historical data
- **Input-Output**: Input-Output (IO) matrices and calculates output changes from new IO matrix and Final Demand (FD) vectors  
- **Household**: variables and parameters related to households and calculates household prices,
            and changes in prices and income  
- **Government**: variables and parameters related to government and calculates government share in trade,
            demand and spending, and changes in demand and spending 
- **Employment**: variables and parameters related to employment and calculates base employment,
            employment constraints, and employment changes
- **Investment**: variables and parameters related to investment and calculates investment shares,
            induced investment, recycled investment, and exogenous investment
- **GDP**: variables and parameters related to GDP and calculates base GVA
            and GVA changes
- **Price Module**: variables and parameters related to prices and calculates 
            prices based on exogenous costs
- **Border Trade Adjustment (BTA) Module**: variables and parameters related to BTA and calculates 
            border trade adjustments based on exogenous costs
- **Trade Module**: variables and parameters related to trade and calculates 
            GDP and price dynamics, and applies elasticities to FD and trade IO coefficients.
- **Income Module**: variables and parameters related to income and calculates investment shares,
            induced investment, recycled investment, and exogenous investment
- **Energy Balances Module**: variables and parameters related to energy balances and emissions and calculates energy flows,
            energy and emissions intensities, energy substitution and emissions by actor.

## Model Setup

1. Create a new regional aggregation file in the `GLORIA_template\Country_groupings` subfolder that defines how the 163 MINDSET regions should be collapsed. The easiest way to create a new grouping file is to copy one of the existing one and adjust the `country_groups` sheet.
2. Change the name of the regional aggregation file in the `collapse_regions.cmd` file:
```bash
python "ParseCode\collapse_MRIO.py" "GLORIA_template\Country_groupings\new_grouping_file.xlsx"
python "ParseCode\collapse_FTT.py" "GLORIA_template\Country_groupings\new_grouping_file.xlsx"
```
3. Run the `collapse_regions.cmd` file. This command prompt creates the file for the new regional aggregates.
4. Create a new scenario input file in the `GLORIA_template\Scenarios` subfolder that defines the scenario assumptions. The easiest way to create a new scenario file is to copy one of the existing one and adjust the corresponding sheet. On each sheet of the .xslx file there is a sample of how scenario assumptions can be added to the model.
5. Once all the inputs for the model are created, the model can be run from the command line with the following command. Alternatively, the model can be run from a Python IDE by running the `MINDSET_dynamic_run.py` script.
```bash
python MINDSET_dynamic_run.py "Scenario_Name" "Yes"
```


