import math
import unittest
import pandas as pd
from WallsEC2 import WallDesigner,clean_dataframe,WallsEC2App

class MissingTensorClosure(unittest.TestCase):
    def designer(self,**kw):
        return WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',wk_check_enabled=True,axial_convention='Tracção positiva',**kw)
    def row(self):
        return dict(panel=1,node=1,case=302,mxx=10,myy=3,mxy=0,qxx=20,qyy=30,nxx=100,nyy=50,nxy=0)
    def test_swap_availability(self):
        row=self.row();del row['qyy'];row['case']=101
        r=self.designer(swap_local_axes=True).design_one(clean_dataframe(pd.DataFrame([row])).iloc[0])
        self.assertTrue(math.isnan(r['QXX_kN_m']));self.assertEqual(r['QYY_kN_m'],20)
        self.assertEqual(r['QXX_raw'],20);self.assertTrue(math.isnan(r['QYY_raw']))
        self.assertTrue(math.isnan(r['util_Qx']));self.assertGreater(r['util_Qy'],0)
    def test_swap_other_missing(self):
        row=self.row();del row['qxx'];row['case']=101
        r=self.designer(swap_local_axes=True).design_one(clean_dataframe(pd.DataFrame([row])).iloc[0])
        self.assertTrue(math.isnan(r['QYY_kN_m']));self.assertEqual(r['QXX_kN_m'],30)
        self.assertTrue(math.isnan(r['QXX_raw']));self.assertEqual(r['QYY_raw'],30)
    def test_partial_membrane_cannot_assign_wk(self):
        for missing in ('nxx','nyy','nxy'):
            row=self.row();del row[missing]
            for zeros in (False,True):
                if zeros:
                    row.update({c:0 for c in ('nxx','nyy','nxy') if c in row})
                r=self.designer().design_one(clean_dataframe(pd.DataFrame([row])).iloc[0])
                self.assertTrue(math.isnan(r['wk_max_mm']))
                self.assertEqual(r['Crack_control_status'],'Não avaliado')
                self.assertEqual(r['Crack_model'],'Não avaliado')
                self.assertIn('membrana incompleta',r['Crack_control_note'])
    def test_wa_without_original_tensor(self):
        row=self.row()
        for c in ('mxx','myy','mxy','nxx','nyy','nxy'):del row[c]
        row.update(mxx_pos_wa=10,mxx_neg_wa=0,myy_pos_wa=3,myy_neg_wa=0)
        r=self.designer().design_one(clean_dataframe(pd.DataFrame([row])).iloc[0])
        self.assertTrue(math.isnan(r['wk_max_mm']))
        self.assertEqual(r['Crack_model'],'Não avaliado')
    def test_complete_row_retains_local_wk(self):
        r=self.designer().design_one(clean_dataframe(pd.DataFrame([self.row()])).iloc[0])
        self.assertTrue(math.isfinite(r['wk_max_mm']))
    def test_partial_membrane_car_no_fake_stresses(self):
        row=self.row();row['case']=303;del row['nxy']
        d=self.designer(characteristic_cases='303')
        r=d.design_one(clean_dataframe(pd.DataFrame([row])).iloc[0])
        self.assertTrue(math.isnan(r['ELS_X_sigma_plus_MPa']))
        self.assertIn('completar a tabela de membrana',r['Verification_reason'])
