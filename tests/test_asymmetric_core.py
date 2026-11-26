import unittest
import numpy as np
from wall_physical_layers import PhysicalCapacity,layout
from wall_asymmetric_core import AsymmetricCore,exterior_actions
from wall_coupled_shear import truss_increment

class AsymmetricTests(unittest.TestCase):
    def setUp(self):
        self.h=250.;self.f=layout(self.h,30,[[(1,12,200)]]*4)
    def test_net_area_and_disjoint_bands(self):
        model=PhysicalCapacity(self.h,self.f,435,10,subdivisions=6,net_area=True,band_fractions=(.5,.3))
        self.assertAlmostEqual(model.core_mm,50)
        self.assertAlmostEqual(model.core_z_mm,-25)
        self.assertAlmostEqual(sum(model.cap)/10,200-sum(f.bar.area_mm2_m for f in self.f)/1000)
        z=np.array(model.geometric_centers);w=np.array(model.widths)
        self.assertAlmostEqual(min(z[:6]-w[:6]/2)-max(z[6:]+w[6:]/2),50)
    def test_exact_pure_compression_limit_with_eccentricity(self):
        model=PhysicalCapacity(self.h,self.f,435,10,subdivisions=6,net_area=True,band_fractions=(.5,.3))
        n=[-sum(model.cap),0,0];m=[-np.dot(model.cap,model.centers)/1000,0,0]
        u,res,_=model.check(n,m)
        self.assertAlmostEqual(u,1.,places=8);self.assertLess(res,1e-6)
    def test_overlapping_bands_rejected(self):
        with self.assertRaises(ValueError):PhysicalCapacity(self.h,self.f,435,10,band_fractions=(.6,.4))
    def test_missing_bar_coverage_rejected(self):
        with self.assertRaises(ValueError):PhysicalCapacity(self.h,self.f,435,10,net_area=True,band_fractions=(.05,.7))
    def test_eccentric_truss_equilibrium(self):
        n=np.array([-200,-300,15]);m=np.array([20,-30,4]);q=np.array([60.,80.]);cot=1.5;z=-25
        nn,mm=exterior_actions(n,m,q,cot,z)
        delta=truss_increment(q,cot)
        np.testing.assert_allclose(nn-delta,n);np.testing.assert_allclose(mm-delta*z/1000,m)
    def test_reflection(self):
        model=AsymmetricCore(self.h,self.f,30,20,500,435)
        n=[-250,-800,-200];m=[-20,-60,-5];q=[30,50]
        a=model.assess(n,m,q,200);b=model.assess(n,-np.array(m),q,200)
        self.assertAlmostEqual(a.face_util,b.face_util,places=7)
        self.assertAlmostEqual(a.core_z_mm,-b.core_z_mm,places=7)
        self.assertAlmostEqual(a.core_mm,b.core_mm)
    def test_separate_shear_explicit(self):
        model=AsymmetricCore(self.h,self.f,30,20,500,435)
        a=model.assess([-250,-800,-200],[-20,-60,-5],[30,50],200)
        self.assertIn('separadamente',a.status);self.assertLess(a.face_util,1)
        self.assertEqual(a.asw_proposed,0.)
    def test_truss_reserve_and_proposal(self):
        model=AsymmetricCore(self.h,self.f,30,20,500,435)
        a=model.assess([-200,-200,0],[1,2,0],[60,80],20)
        self.assertIn('Proposta experimental',a.status);self.assertLessEqual(a.face_util,1)
        self.assertLessEqual(a.core_util,1);self.assertGreaterEqual(a.asw_proposed,a.asw_required)
        self.assertAlmostEqual(a.core_mm,50)
    def test_extreme_shear_no_solution(self):
        model=AsymmetricCore(self.h,self.f,30,20,500,435)
        a=model.assess([0,0,0],[0,0,0],[1000,1000],10)
        self.assertIn('Sem solução',a.status)
    def test_integration_keeps_original_warning(self):
        from unittest.mock import patch
        import pandas as pd
        from WallsEC2 import WallDesigner,clean_dataframe,WallsEC2App
        from wall_core_equilibrium import CoreTrial
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',axial_convention='Tracção positiva',wk_check_enabled=True)
        d.shell_qp_diagnostic=True
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,nxx=-20,nyy=30,nxy=5,mxx=10,myy=5,mxy=1,qxx=0,qyy=0) for c in (101,302,303,311)]))
        with patch('wall_core_equilibrium.CoreEquilibrium.assess',return_value=CoreTrial('Sem solução; ensaio',face_util=1.1)):
            r=d.design_dataframe(df)
        self.assertIn('Sem solução',r.iloc[0].Core_status)
        self.assertLess(r.iloc[0].Asym_face_util,1)
        state,reason=WallsEC2App.panel_outcome(r)
        self.assertEqual(state,'Incompleto');self.assertIn('solução não demonstrada',reason)
