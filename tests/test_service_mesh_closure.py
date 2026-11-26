import math
import unittest
import pandas as pd
from WallsEC2 import WallDesigner,clean_dataframe

class ServiceMeshClosure(unittest.TestCase):
    def setUp(self):
        self.d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',wk_check_enabled=True,axial_convention='Tracção positiva',optimize_rebar=True,base_vertical_phi=12,base_horizontal_phi=12,base_vertical_spacing=200,base_horizontal_spacing=200,phi_max_mm=20)
        self.mesh=[self.d.base_solution_for_direction(i>=2) for i in range(4)]
        self.df=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=302,nxx=-50,nyy=400,nxy=0,mxx=3,myy=0,mxy=0,qxx=0,qyy=0)]))
    def test_partial_face_still_drives_verified_sizing(self):
        before=self.d.design_one(self.df.iloc[0],self.mesh,skip_shell_diagnostic=True)
        self.assertEqual(before['Crack_model'],'N-M fendilhado parcial');self.assertTrue(math.isnan(before['wk_max_mm']));self.assertGreater(before['wk_partial_max_mm'],.3)
        self.assertEqual(self.d.refine_service_mesh(self.df,{'1':self.mesh}),{'1'})
        after=self.d.design_one(self.df.iloc[0],self.mesh,skip_shell_diagnostic=True)
        self.assertLessEqual(after['wk_partial_max_mm'],.3);self.assertTrue(math.isnan(after['wk_max_mm']));self.assertTrue(all('Ø12//200' in v.text for v in self.mesh))
    def test_inclined_unvalidated_does_not_drive_sizing(self):
        self.df['nxy']=1.
        before=tuple(v.text for v in self.mesh);self.assertEqual(self.d.refine_service_mesh(self.df,{'1':self.mesh}),set());self.assertEqual(tuple(v.text for v in self.mesh),before)
    def test_reduction_rejected(self):
        self.assertFalse(self.d.service_candidate_fits(self.mesh,2,self.d.rebar_from_phi_spacing(8,200)))
