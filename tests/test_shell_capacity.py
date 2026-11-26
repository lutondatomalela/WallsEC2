import unittest
import numpy as np
from wall_shell_capacity import face_state,check
from wall_crack_diagnostic import diagnose

class CapacityTests(unittest.TestCase):
    def test_pure_tension(self):
        r=check([200,0,0],[0,0,0],[1000]*4,250,150,400,10)
        self.assertAlmostEqual(float(r['Capacity_trial_util']),.25,places=6)
    def test_pure_shear(self):
        # Steel needed q in each direction, concrete trace 2q per face.
        r=check([0,0,100],[0,0,0],[1000]*4,250,150,400,10)
        self.assertAlmostEqual(float(r['Capacity_trial_util']),.125,places=6)
    def test_compression_governs(self):
        r=check([-2000,0,0],[0,0,0],[1000]*4,250,150,400,10)
        self.assertAlmostEqual(float(r['Capacity_trial_util']),1.,places=5)
    def test_unequal_steel_redistributes(self):
        ok,a,b=face_state([0,0,100],[50,250],300)
        self.assertTrue(ok); self.assertAlmostEqual(a,50); self.assertAlmostEqual(b,200)
        self.assertFalse(face_state([0,0,100],[50,150],300)[0])
    def test_equilibrium_random(self):
        rng=np.random.default_rng(51); n=rng.normal(size=(200,3))*40; m=rng.normal(size=(200,3))*5
        r=check(n,m,np.full((200,4),1000),250,150,400,10)
        self.assertTrue(r['Capacity_trial_ok'].all())
        for j,key in enumerate(('xx','yy','xy')):
            f=[]
            for face in ('plus','minus'):
                c=r[f'Capacity_C{key}_{face}_kN_m']; t=0 if j==2 else r[f'Capacity_T{key[0]}_{face}_kN_m']; f.append(c+t)
            np.testing.assert_allclose(f[0]+f[1],n[:,j],atol=1e-10)
            np.testing.assert_allclose((f[0]-f[1])*.075,m[:,j],atol=1e-10)
    def test_crack_shear_sign_invariance(self):
        def r(q):return diagnose(250,[0,0,q],[0,0,0],[1000]*4,45,30000,[(12,100)]*4)
        a,b=r(60),r(-60)
        self.assertGreater(a['ShellQP_indicator_max_mm'],0)
        self.assertAlmostEqual(a['ShellQP_indicator_max_mm'],b['ShellQP_indicator_max_mm'],places=7)
    def test_automatic_mesh_and_governing_state(self):
        import pandas as pd
        from WallsEC2 import WallDesigner,clean_dataframe,WallsEC2App
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101-102',axial_convention='Tracção positiva',phi_max_mm=20, optimize_rebar=True)
        rows=[dict(panel=1,node=1,case=101,mxx=10,myy=0,mxy=0,qxx=0,qyy=0,nxx=50,nyy=0,nxy=250),dict(panel=1,node=1,case=102,mxx=1,myy=0,mxy=0,qxx=0,qyy=0,nxx=-10,nyy=0,nxy=0)]
        r=d.design_dataframe(clean_dataframe(pd.DataFrame(rows)))
        self.assertTrue(r.Capacity_trial_util.notna().all())
        self.assertGreaterEqual(r.iloc[0]['Asx+_prov_mm2_m'],(25+10*1000/(250-2*(30+30))+125)*1000/d.fyd-1e-8)
        e=WallsEC2App.build_nm_envelope(r)
        for _,row in e.iterrows():
            governing=r[(r.Case==row.Case)&(r.Node==row.Node)].iloc[0]
            self.assertEqual(row['Segunda ordem'],governing['Stability_'+row['Direcção']+'_status'])
