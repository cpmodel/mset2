import unittest

import numpy as np
import pandas as pd

from SourceCode.investment import invest


class FTTInvestmentChangeTests(unittest.TestCase):
    def setUp(self):
        self.model = invest.__new__(invest)
        self.model.R_list = ['A', 'B']
        self.model.P_list = [1, 2, 93]
        self.model.investment_induced = pd.DataFrame([
            ('A', 93, 'A', 1, 50.0),
            ('A', 5, 'A', 93, 7.0),
            ('A', 5, 'A', 1, 3.0),
            ('B', 5, 'B', 2, 4.0),
        ], columns=['REG_imp', 'PROD_COMM', 'REG_exp', 'TRAD_COMM', 'dy'])
        self.model.fcf_share = pd.DataFrame([
            ('A', 1, 'A', 0.75), ('A', 1, 'B', 0.25),
            ('A', 2, 'A', 0.25), ('A', 2, 'B', 0.75),
            ('B', 1, 'B', 1.0),
        ], columns=['REG_imp', 'TRAD_COMM', 'REG_exp', 'FCF_share'])
        self.base = pd.DataFrame([
            ('B', 93, 50.0), ('A', 93, 100.0), ('A', 5, 200.0),
        ], columns=['REG_imp', 'PROD_COMM', 'dk_base'])
        self.flows = pd.DataFrame([
            ('A', 5, 'A', 93, 30.0), ('A', 5, 'B', 93, 70.0),
            ('A', 93, 'A', 93, 1000.0),
        ], columns=['REG_imp', 'PROD_COMM', 'REG_exp', 'TRAD_COMM', 'z_bp']).set_index(
            ['REG_imp', 'PROD_COMM', 'REG_exp', 'TRAD_COMM']
        )

    def test_replaces_only_electricity_sector_and_preserves_product_mix_changes(self):
        previous = np.array([[120.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
        current = np.array([[110.0, 20.0, 0.0], [0.0, 0.0, 0.0]])
        self.model.replace_electricity_investment_change(previous, current, self.base, self.flows)

        result = self.model.investment_induced.set_index(
            ['REG_imp', 'PROD_COMM', 'REG_exp', 'TRAD_COMM']
        )['dy']
        self.assertAlmostEqual(result.loc['A', 93, 'A', 1], -6.25)
        self.assertAlmostEqual(result.loc['A', 93, 'B', 1], -100 / 48)
        self.assertAlmostEqual(result.loc['A', 93, 'A', 2], 100 / 24)
        self.assertAlmostEqual(result.loc['A', 93, 'B', 2], 12.5)
        self.assertAlmostEqual(result.loc['A', 5, 'A', 93], 7.0)
        self.assertAlmostEqual(result.loc['B', 5, 'B', 2], 4.0)
        self.assertAlmostEqual(result.xs(('A', 93), level=('REG_imp', 'PROD_COMM')).sum(),
                               100 * (130 / 120 - 1))
        total = self.model.dy_inv_induced.set_index(['REG_exp', 'TRAD_COMM', 'REG_imp'])['dy']
        self.assertEqual(total.loc['A', 93, 'A'], 7.0)
        self.assertAlmostEqual(total.loc['A', 1, 'A'], -3.25)

    def test_zero_previous_investment_uses_absolute_change(self):
        self.model.replace_electricity_investment_change(
            np.zeros((2, 3)), np.array([[0, 0, 0], [25, 0, 0]]), self.base, self.flows,
        )
        electricity = self.model.investment_induced.query('REG_imp == "B" and PROD_COMM == 93')
        self.assertAlmostEqual(electricity['dy'].sum(), 25)
        self.assertEqual(electricity.iloc[0]['REG_exp'], 'B')

    def test_product_mix_can_change_even_when_total_investment_does_not(self):
        self.model.replace_electricity_investment_change(
            np.array([[120, 0, 0], [0, 0, 0]]),
            np.array([[60, 60, 0], [0, 0, 0]]),
            self.base, self.flows,
        )
        electricity = self.model.investment_induced.query('PROD_COMM == 93')
        by_product = electricity.groupby('TRAD_COMM')['dy'].sum()
        self.assertAlmostEqual(by_product.loc[1], -50)
        self.assertAlmostEqual(by_product.loc[2], 50)
        self.assertAlmostEqual(by_product.sum(), 0)

    def test_missing_investment_shares_use_other_sectors_trade(self):
        self.model.replace_electricity_investment_change(
            np.array([[120, 0, 0], [0, 0, 0]]),
            np.array([[120, 0, 12], [0, 0, 0]]),
            self.base, self.flows,
        )
        electricity = self.model.investment_induced.query('PROD_COMM == 93').set_index('REG_exp')
        self.assertAlmostEqual(electricity.loc['A', 'dy'], 3)
        self.assertAlmostEqual(electricity.loc['B', 'dy'], 7)

    def test_missing_supplier_flows_are_not_silently_discarded(self):
        with self.assertRaisesRegex(ValueError, 'allocate FTT investment'):
            self.model.replace_electricity_investment_change(
                np.array([[120, 0, 0], [0, 0, 0]]),
                np.array([[120, 0, 10], [0, 0, 0]]),
                self.base, self.flows.iloc[0:0],
            )


if __name__ == '__main__':
    unittest.main()
