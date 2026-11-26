import unittest
import math
import numpy as np
from wall_physical_layers import layout,PhysicalCapacity
from wall_core_equilibrium import CoreEquilibrium,link_grid
from wall_service_history import classify_history

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.h=250.;self.f=layout(self.h,30,[[(1,12,200)]]*4)
        self.model=CoreEquilibrium(self.h,self.f,30,20,500,435)
    def test_net_area_exact(self):
        for frac in (.30,.35,.40):
            m=PhysicalCapacity(self.h,self.f,435,10,band_fraction=frac,subdivisions=6,net_area=True)
            self.assertAlmostEqual(sum(m.cap)/10,2*frac*self.h-sum(f.bar.area_mm2_m for f in self.f)/1000,places=10)
    def test_zero(self):
        a=self.model.assess([0,0,0],[0,0,0],[0,0],0)
        self.assertEqual(a.face_util,0);self.assertEqual(a.asw_required,0)
        self.assertTrue(math.isnan(a.core_util))
    def test_trellis_core_and_grid(self):
        a=self.model.assess([-200,-200,0],[0,0,0],[80,60],10)
        self.assertIn('Proposta',a.status);self.assertLessEqual(a.core_util,1);self.assertLessEqual(a.face_util,1)
        self.assertGreaterEqual(a.asw_proposed,a.asw_required)
        self.assertAlmostEqual(a.core_util,100/a.core_mm*(a.cot_theta+1/a.cot_theta)/self.model.fc)
        self.assertAlmostEqual(a.asw_proposed,math.pi*a.phi**2/4*1e6/(a.pitch_x*a.pitch_y))
    def test_core_crushing(self):
        a=self.model.assess([0,0,0],[0,0,0],[1000,1000],0)
        self.assertIn('Sem solução',a.status)
    def test_reflection(self):
        a=self.model.assess([-200,-200,10],[1,-2,2],[80,60],10)
        b=self.model.assess([-200,-200,-10],[1,-2,-2],[80,-60],10)
        self.assertAlmostEqual(a.face_util,b.face_util,places=8)
        self.assertAlmostEqual(a.asw_proposed,b.asw_proposed)
    def test_grid_no_solution(self):
        self.assertIsNone(link_grid(1e7,200));self.assertIsNone(link_grid(100,50))
    def test_invalid(self):
        self.assertIn('insuficientes',self.model.assess([0,0,0],[0,0,0],[np.nan,0],0).status)
    def test_history(self):
        a=classify_history([.5,1.2],2.9,complete=True);self.assertEqual(a.wk_conditional_mm,0);self.assertIn('apenas',a.status)
        self.assertTrue(math.isnan(classify_history([2.1],2.9,complete=True).wk_conditional_mm))
        self.assertTrue(math.isnan(classify_history([.1],2.9,complete=False).wk_conditional_mm))
        self.assertTrue(math.isnan(classify_history([np.nan],2.9,complete=True).wk_conditional_mm))
    def test_integration_no_false_verdict(self):
        import pandas as pd
        from WallsEC2 import WallDesigner,clean_dataframe
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',axial_convention='Tracção positiva',wk_check_enabled=True)
        d.shell_qp_diagnostic=True
        r=d.design_dataframe(clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,nxx=-20,nyy=30,nxy=5,mxx=10,myy=5,mxy=1,qxx=0,qyy=0) for c in (101,302,303,311)])))
        self.assertTrue(r.iloc[0].Core_status.startswith('Equilíbrio'))
        self.assertTrue(np.isnan(r.iloc[1].wk_max_mm));self.assertIn('History_plus_status',r)

    def test_band_failure_does_not_block_els(self):
        from unittest.mock import patch
        import pandas as pd
        from WallsEC2 import WallDesigner,clean_dataframe
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',axial_convention='Tracção positiva',wk_check_enabled=True)
        d.shell_qp_diagnostic=True
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,nxx=-20,nyy=30,nxy=5,mxx=10,myy=5,mxy=1,qxx=0,qyy=0) for c in (101,302,303,311)]))
        with patch('wall_physical_layers.PhysicalCapacity',side_effect=ValueError('banda insuficiente')):
            r=d.design_dataframe(df)
        self.assertTrue(np.isnan(r.iloc[0].PhysELU_util));self.assertIn('indisponível',r.iloc[0].PhysELU_status)
        self.assertTrue(np.isfinite(r.iloc[1].PhysCracked_sigma_s_MPa));self.assertTrue(np.isnan(r.iloc[1].wk_max_mm))
