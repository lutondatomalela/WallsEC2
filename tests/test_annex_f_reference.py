import unittest
import numpy as np
from wall_annex_f import membrane_reference,nominal_shell_reference

class AnnexFReference(unittest.TestCase):
    def check(self,n,cap=(1000,1000),h=100):return membrane_reference(n,cap,h,30,20)
    def test_pure_tension_and_pure_shear(self):
        for n,t,c in [([50,100,0],[50,100],[0,0,0]),([0,0,100],[100,100],[-100,-100,100])]:
            r=self.check(n);self.assertTrue(r['ok']);np.testing.assert_allclose(r['steel_opt'],t);np.testing.assert_allclose(r['steel'],t);np.testing.assert_allclose(r['concrete'],c)
    def test_two_compressive_principal_stresses(self):
        r=self.check([-1500,-1500,200],(0,0))
        self.assertTrue(r['ok']);self.assertAlmostEqual(r['concrete_stress_mpa'],17.);self.assertEqual(r['concrete_limit_mpa'],20.)
        self.assertFalse(self.check([-2100,-1500,200])['ok'])
    def test_second_branch(self):
        r=self.check([-200,100,100]);np.testing.assert_allclose(r['steel_opt'],[0,150]);self.assertTrue(r['ok']);self.assertAlmostEqual(r['concrete_stress_mpa'],2.5)
        np.testing.assert_allclose(r['steel'],[0,150]);np.testing.assert_allclose(r['concrete'],[-200,-50,100])
    def test_redistribution_bounds(self):
        r=self.check([0,0,100],(50,200));self.assertTrue(r['ok']);np.testing.assert_allclose(r['steel'],[50,200])
        self.assertFalse(self.check([0,0,100],(40,300))['ok'])
    def test_swapping_axes_and_reflection(self):
        a=self.check([-200,100,100]);b=self.check([100,-200,-100]);np.testing.assert_allclose(a['steel'],b['steel'][::-1]);self.assertAlmostEqual(a['concrete_stress_mpa'],b['concrete_stress_mpa'])
    def test_random_equilibrium(self):
        rng=np.random.default_rng(232)
        n=rng.normal(size=(2000,3))*200;cap=rng.uniform(0,1000,(2000,2));r=membrane_reference(n,cap,100,30,20);yes=r['ok'];self.assertGreater(yes.sum(),500)
        np.testing.assert_allclose(r['concrete'][yes]+np.column_stack([r['steel'][yes],np.zeros(yes.sum())]),n[yes],atol=1e-7)
        for v in r['concrete'][yes]:self.assertLessEqual(np.linalg.eigvalsh([[v[0],v[2]],[v[2],v[1]]]).max(),1e-7)
        self.assertTrue((r['steel'][yes]<=cap[yes]+1e-7).all());self.assertTrue((r['steel'][yes]>=.5*r['steel_opt'][yes]-1e-7).all());self.assertTrue((r['steel'][yes]<=2*r['steel_opt'][yes]+1e-7).all())
    def test_shell_equilibrium(self):
        n=np.array([100,20,5]);m=np.array([10,2,-4]);p,b=nominal_shell_reference(n,m,[1500]*4,250,150,30,20,435)
        self.assertTrue(p['ok'] and b['ok']);f=lambda r:r['concrete']+np.r_[r['steel'],0.]
        np.testing.assert_allclose(f(p)+f(b),n);np.testing.assert_allclose((f(p)-f(b))*.075,m)
    def test_integration_does_not_grant_shell_verdict(self):
        import pandas as pd
        from WallsEC2 import WallDesigner,clean_dataframe,WallsEC2App
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',wk_check_enabled=True,axial_convention='Tracção positiva')
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,nxx=-20,nyy=30,nxy=5,mxx=10,myy=5,mxy=1,qxx=0,qyy=0) for c in (101,302)]))
        r=d.design_dataframe(df)
        self.assertTrue(r.iloc[0].AnnexF_nominal_ok)
        self.assertIn('não é ELU de casca',r.iloc[0].AnnexF_nominal_status)
        self.assertEqual(WallsEC2App.panel_outcome(r)[0],'Incompleto')
