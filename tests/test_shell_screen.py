import unittest
import numpy as np
import pandas as pd
from wall_shell_screen import screen, envelope
from WallsEC2 import WallDesigner, clean_dataframe

class ShellScreenTests(unittest.TestCase):
    def test_pure_membrane_shear(self):
        d=screen([0,0,100],[0,0,0],150,[1000]*4,400)
        for f in ('plus','minus'):
            self.assertAlmostEqual(d[f'Screen_Asx_{f}_mm2_m'],125)
            self.assertAlmostEqual(d[f'Screen_Asy_{f}_mm2_m'],125)
            self.assertAlmostEqual(d[f'Screen_C1_{f}_kN_m'],0)
            self.assertAlmostEqual(d[f'Screen_C2_{f}_kN_m'],-100)
    def test_pure_bending(self):
        d=screen([0,0,0],[60,0,0],150,[1000]*4,400)
        self.assertAlmostEqual(d['Screen_Asx_plus_mm2_m'],1000)
        self.assertEqual(d['Screen_Asx_minus_mm2_m'],0)
    def test_equilibrium_and_compression(self):
        rng=np.random.default_rng(17)
        n=rng.normal(size=(1000,3))*500; m=rng.normal(size=(1000,3))*100
        d=screen(n,m,150,np.full((1000,4),1000),435)
        for j,a in enumerate(('x','y','xy')):
            p=d[f'Screen_F{a}_plus_kN_m']; q=d[f'Screen_F{a}_minus_kN_m']
            np.testing.assert_allclose(p+q,n[:,j],atol=1e-10)
            np.testing.assert_allclose((p-q)*.075,m[:,j],atol=1e-10)
        self.assertLessEqual(max(d['Screen_C1_plus_kN_m'].max(),d['Screen_C1_minus_kN_m'].max()),1e-10)
    def test_swap_faces_and_shear_sign(self):
        n=[100,-200,70]; m=[30,40,-22]; a=[600,700,800,900]
        d=screen(n,m,150,a,435); b=screen(n,[-x for x in m],150,[700,600,900,800],435)
        self.assertAlmostEqual(d['Screen_ratio_x_plus'],b['Screen_ratio_x_minus'])
        c=screen([100,-200,-70],[30,40,22],150,a,435)
        self.assertAlmostEqual(d['Screen_ratio_max'],c['Screen_ratio_max'])
    def test_missing_tensor_never_screened(self):
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',axial_convention='Tracção positiva')
        row=dict(panel=1,node=1,case=101,mxx=10,myy=2,mxy=0,qxx=1,qyy=2,nxx=0,nyy=0)
        r=d.design_dataframe(clean_dataframe(pd.DataFrame([row])))
        self.assertTrue(r.Screen_ratio_max.isna().all())
        self.assertEqual(envelope(r).iloc[0].diagnosticadas,0)
    def test_input_invalid(self):
        for z in (0,-1,np.nan):
            with self.assertRaises(ValueError): screen([0]*3,[0]*3,z,[1000]*4,435)
