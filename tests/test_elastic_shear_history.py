import unittest
import numpy as np
import pandas as pd
from wall_elastic_shear_history import screen
from wall_physical_layers import elastic_trial,layout

class ElasticShearHistory(unittest.TestCase):
    def test_pure_transverse_shear(self):
        q=np.array([[80.,60.]])
        a=screen(200,np.zeros((1,6)),q,30000.)
        np.testing.assert_allclose(a.tensile_sample_mpa,[[.75,.75]],atol=1e-14)
        np.testing.assert_allclose(a.interpolation_bound_mpa,[.75/1024])
    def test_plane_stress_limit(self):
        f=layout(250,30,[[(1,12,200)]]*4)
        g,p,_=elastic_trial(250,[[10,100,60],[-200,-150,5]],[[20,-10,5],[1,1,0]],f,30000.)
        a=screen(250,g,np.zeros((2,2)),30000.)
        # In a half-thickness affine field the extreme is at the face or midplane.
        mid=g.copy();mid[:,3:]=0
        expected=np.maximum(np.maximum(0,p[:,:,1]),screen(250,mid,np.zeros((2,2)),30000.).tensile_upper_mpa)
        np.testing.assert_allclose(a.tensile_upper_mpa,expected,atol=1e-12)
        self.assertTrue((a.interpolation_bound_mpa==0).all())
    def test_reflection_and_axis_exchange(self):
        g=np.array([[.00002,-.0001,.00004,.0001,.00003,.00008]])
        q=np.array([[80.,-50.]])
        a=screen(220,g,q,30000.)
        b=g.copy();b[:,3:]*=-1
        np.testing.assert_allclose(a.tensile_upper_mpa,screen(220,b,q,30000.).tensile_upper_mpa[:,::-1])
        np.testing.assert_allclose(a.tensile_upper_mpa,screen(220,g[:,[1,0,2,4,3,5]],q[:,::-1],30000.).tensile_upper_mpa)
    def test_grid_bound(self):
        rng=np.random.default_rng(540);g=rng.normal(0,.0001,(100,6));q=rng.uniform(-150,150,(100,2))
        coarse=screen(250,g,q,30000.,intervals=8);fine=screen(250,g,q,30000.,intervals=256)
        self.assertTrue((coarse.tensile_upper_mpa>=fine.tensile_sample_mpa-1e-12).all())
        self.assertTrue((coarse.tensile_sample_mpa<=fine.tensile_sample_mpa+1e-12).all())
    def test_invalid_missing(self):
        a=screen(200,np.zeros((2,6)),[[np.nan,1],[0,0]],30000.)
        self.assertTrue(np.isnan(a.tensile_upper_mpa[0]).all());self.assertTrue((a.tensile_upper_mpa[1]==0).all())
        with self.assertRaises(ValueError):screen(0,np.zeros((1,6)),[[1,1]],30000.)
    def test_integration_does_not_assign_wk(self):
        from WallsEC2 import WallDesigner,clean_dataframe
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',axial_convention='Tracção positiva',wk_check_enabled=True)
        d.shell_qp_diagnostic=True
        r=d.design_dataframe(clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,nxx=0,nyy=0,nxy=1,mxx=0,myy=0,mxy=0,qxx=350 if c==303 else 0,qyy=0) for c in (101,302,303,311)])))
        qp=r[r.Combo_type.eq('ELS-QP')].iloc[0]
        self.assertGreater(qp.History_plus_ratio_fctk005,1.)
        self.assertTrue(np.isnan(qp.History_plus_wk_conditional_mm));self.assertTrue(np.isnan(qp.wk_max_mm))
