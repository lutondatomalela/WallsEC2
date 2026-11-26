import math
import unittest
import numpy as np
import pandas as pd
from wall_physical_layers import layout,elastic_trial,PhysicalCapacity,crack_candidate

class PhysicalLayerTests(unittest.TestCase):
    def setUp(self):
        self.h=250.; self.f=layout(self.h,30,[[(1,10,200)],[(1,10,200)],[(1,12,200),(1,16,200)],[(1,12,200),(1,16,200)]])
    def test_geometry_independent_centres(self):
        self.assertEqual([f.bar.z_mm for f in self.f if f.label=='Y+'],[89.,87.])
        self.assertEqual([f.bar.z_mm for f in self.f if f.label=='X+'],[74.])
        self.assertRaises(ValueError,layout,80,30,[[(1,16,200)]]*4)
    def test_pure_tension(self):
        model=PhysicalCapacity(self.h,self.f,400,10)
        u,res,st=model.check([200,0,0],[0,0,0]); a=2*1000*math.pi*10**2/(4*200)
        self.assertAlmostEqual(u,200/(a*.4),places=7); self.assertLess(res,1e-6)
    def test_minimum_added_capacity(self):
        model=PhysicalCapacity(self.h,self.f,400,10)
        a=model.required_areas([600,0,0],[0,0,0])
        np.testing.assert_allclose(a[:2],[750,750],atol=1e-7)
        self.assertIsNone(model.required_areas([-3000,0,0],[0,0,0]))
        b=model.required_areas([50,0,0],[0,0,0])
        np.testing.assert_allclose(b,[sum(f.bar.area_mm2_m for f in self.f if f.label==k) for k in ('X+','X-','Y+','Y-')])
    def test_compression(self):
        model=PhysicalCapacity(self.h,self.f,400,10)
        u,res,st=model.check([-1000,0,0],[0,0,0])
        self.assertAlmostEqual(u,1000/sum(model.cap),places=7)
    def test_reflection(self):
        model=PhysicalCapacity(self.h,self.f,400,10)
        a=model.check([-200,-100,55],[5,-10,9]);b=model.check([-200,-100,-55],[5,-10,-9])
        self.assertAlmostEqual(a[0],b[0],places=8);self.assertLess(a[1],1e-6)
    def test_elastic_shear(self):
        _,p,s=elastic_trial(self.h,[0,0,100],[0,0,0],self.f,30000)
        area=sum(f.bar.area_mm2_m for f in self.f)/1000
        np.testing.assert_allclose(p,[[-100/(self.h-area),100/(self.h-area)]]*2,atol=1e-10)
        np.testing.assert_allclose(s,0,atol=1e-10)
    def test_elastic_axial(self):
        q,p,s=elastic_trial(self.h,[200,0,0],[0,0,0],self.f,30000,nu=0.)
        area=sum(f.bar.area_mm2_m for f in self.f)/1000; ax=sum(f.bar.area_mm2_m for f in self.f if f.bar.axis==0)/1000
        self.assertAlmostEqual(q[0],200/(30000*(self.h-area)+200000*ax),places=13)
    def test_crack_no_verdict(self):
        r=crack_candidate(self.h,self.f,[100,200,0],[0,0,0],30000,2.9,fyk=500)
        self.assertIn('wk pendente',r['PhysQP_status']);self.assertNotIn('wk_max_mm',r)
        self.assertTrue(np.isfinite(r['PhysQP_candidate_max_mm']))
    def test_yield_guard(self):
        r=crack_candidate(self.h,self.f,[1000,200,0],[0,0,0],30000,2.9,fyk=500)
        self.assertIn('fora do domínio',r['PhysQP_status']);self.assertNotIn('PhysQP_candidate_max_mm',r)
    def test_integrated_all_roles(self):
        from WallsEC2 import WallDesigner,clean_dataframe
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',axial_convention='Tracção positiva',wk_check_enabled=True)
        d.shell_qp_diagnostic=True
        r=d.design_dataframe(clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,nxx=-20,nyy=30,nxy=5,mxx=10,myy=5,mxy=1,qxx=0,qyy=0) for c in (101,302,303,311)])))
        self.assertTrue(np.isfinite(r.iloc[0].PhysELU_util));self.assertTrue(r.iloc[1:].PhysCracked_sigma_s_MPa.notna().all())
        self.assertTrue(np.isnan(r.iloc[1].wk_max_mm));self.assertTrue(np.isfinite(r.iloc[2].PhysCracked_ratio_s_08fyk))
