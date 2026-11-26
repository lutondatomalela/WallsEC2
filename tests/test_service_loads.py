import unittest
import pandas as pd
from WallsEC2 import WallDesigner,clean_dataframe,format_case_ranges,compact_panel_reason

class ServiceLoadTests(unittest.TestCase):
    def run_case(self,large=False,omit=False):
        d=WallDesigner(200,40,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',axial_convention='Tracção positiva',wk_check_enabled=True)
        d.sandwich_design=True
        data=[dict(panel=1,node=1,case=c,mxx=1,myy=.5,mxy=.2,nxx=5,nyy=5,nxy=2 if not (large and c==303) else 1000,qxx=1,qyy=1) for c in [101,302,303,311] if not (omit and c==303)]
        return d.design_dataframe(clean_dataframe(pd.DataFrame(data)))
    def test_low_stress_conditional_not_normative(self):
        r=self.run_case();q=r[r.Combo_type.eq('ELS-QP')].iloc[0]
        self.assertEqual(q.wk_cargas_cond_mm,0)
        self.assertTrue(pd.isna(q.wk_max_mm))
        self.assertLess(q.ELS_historico_ratio,1)
    def test_history_and_missing(self):
        for r in (self.run_case(large=True),self.run_case(omit=True)):
            self.assertTrue(r.wk_cargas_cond_mm.isna().all())
    def test_ranges(self):
        self.assertEqual(format_case_ranges(['10','11','12','15']),'10–12, 15')
        self.assertIn('6.109',compact_panel_reason('sandwich: condições da secção 6.109 não demonstradas; limite conservador de triagem'))
