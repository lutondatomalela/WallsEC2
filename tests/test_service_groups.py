import unittest
import pandas as pd
from WallsEC2 import WallDesigner, clean_dataframe, ec2_final_creep

class ServiceGroupTests(unittest.TestCase):
    def test_groups_and_steel(self):
        d = WallDesigner(250, 40, "C30/37", 500, elu_cases="101", qp_case="302",
                         characteristic_cases="303", frequent_cases="304",
                         axial_convention="Tracção positiva", wk_check_enabled=True)
        rows = [dict(panel=1,node=1,case=c,mxx=10,myy=2,mxy=0,
                     nxx=0,nyy=0,nxy=0,qxx=0,qyy=0) for c in (101,302,303,304)]
        result = d.design_dataframe(clean_dataframe(pd.DataFrame(rows)))
        self.assertEqual(result.Combo_type.tolist(), ["ELU","ELS-QP","ELS-CAR","ELS-FREQ"])
        self.assertTrue(result.iloc[2:]["ELS_X_sigma_plus_MPa"].notna().all())
        self.assertTrue(result.iloc[2:]["wk_max_mm"].isna().all())
        self.assertTrue(result.iloc[2:]["util_M"].isna().all())

    def test_creep_saturated_air(self):
        self.assertAlmostEqual(ec2_final_creep(22,100,250,28),
                               16.8/30**.5/(0.1+28**.2))
        self.assertGreater(ec2_final_creep(30,50,250,28),ec2_final_creep(30,80,250,28))
