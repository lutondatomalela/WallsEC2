"""Independent equilibrium, limiting cases and integration for simplified LL/F design."""
import unittest
import numpy as np
import pandas as pd
from wall_sandwich_design import face_opt, layers, solve_faces, assess
from wall_physical_layers import layout
from wall_coupled_shear import truss_increment
from WallsEC2 import WallDesigner, WallsEC2App, clean_dataframe

class SandwichTests(unittest.TestCase):
    def setUp(self):
        self.h=250.; self.fck=30.;self.fcd=20.;self.fyd=500/1.15
        self.f=layout(self.h,30,[[(1,12,200)]]*4)
    def test_annex_f_pure_shear_and_compression_branch(self):
        n=np.array([[0.,0,100],[-200,-10,100],[-200,-100,100],[30,60,0],[-10,20,0]])
        np.testing.assert_allclose(face_opt(n),[[100,100],[0,40],[0,0],[30,60],[0,20]])
    def test_pure_axial_tension_eccentricity(self):
        ls=layers(self.h,self.f,(70.,80.));n=np.array([[200.,100.,0.]])
        # All N carried by orthogonal bars with known z positions; independent statics.
        sp=np.array([140.,30.]);sm=n[0,:2]-sp
        m=np.array([[*(ls[0][3]*sp+ls[1][3]*sm)/1000,0.]])
        req,us,uc,res,ok,p,b=solve_faces(n,m,ls,self.fck,self.fcd,self.fyd)
        np.testing.assert_allclose(req[0]*self.fyd/1000,[140,60,30,70],atol=1e-6)
        self.assertTrue(ok[0]);self.assertAlmostEqual(uc[0],0.);self.assertLess(res[0],1e-7)
    def test_pure_moment_static_couple(self):
        ls=layers(self.h,self.f,(70.,80.));n=np.zeros((1,3));m=np.array([[25.,0.,0.]])
        t=25000/(ls[0][3][0]-ls[1][1])
        req,us,uc,res,ok,p,b=solve_faces(n,m,ls,self.fck,self.fcd,self.fyd)
        self.assertAlmostEqual(req[0,0]*self.fyd/1000,t,places=6);self.assertAlmostEqual(req[0,1],0.)
        self.assertTrue(ok[0]);self.assertAlmostEqual(-b[0,0],t,places=6)
    def test_asymmetric_eccentricity_and_net_area(self):
        ls=layers(self.h,self.f,(60.,110.));a=sum(x.bar.area_mm2_m/1000 for x in self.f)
        self.assertAlmostEqual(ls[0][0]+ls[1][0],170-a)
        for side,L,t in zip((1,-1),ls,(60,110)):
            f=[x for x in self.f if x.bar.z_mm*side>0]
            self.assertAlmostEqual(L[0]*L[1],side*t*(self.h/2-t/2)-sum(x.bar.area_mm2_m/1000*x.bar.z_mm for x in f))
    def test_coupled_trellis_and_equilibrium(self):
        n=np.array([[-20.,15,10.]]);m=np.array([[3.,-2.,1.]]);q=np.array([[140.,160.]])
        r=assess(self.h,self.f,n,m,q,self.fck,self.fcd,1.5,500,self.fyd)
        self.assertGreater(r['Asw_req_mm2_m2'][0],0.);self.assertLess(r['residual_kNm_m'][0],1e-7)
        delta=truss_increment(q)[0];p=np.array([r['Nplus_'+j][0] for j in ('x','y','xy')]);b=np.array([r['Nminus_'+j][0] for j in ('x','y','xy')]);np.testing.assert_allclose(p+b-delta,n[0],atol=1e-8)
        z=min(r['z_mm'][0],r['core_mm'][0]);self.assertGreaterEqual(r['Asw_req_mm2_m2'][0]*z*self.fyd/1e6,np.linalg.norm(q)-1e-9)
        self.assertIn('proposta',r['status'][0])
    def test_reflection(self):
        n=np.array([[-50.,60,8.]]);m=np.array([[13.,-7,3.]]);q=np.array([[10.,-20.]])
        a=assess(self.h,self.f,n,m,q,self.fck,self.fcd,1.5,500,self.fyd)
        b=assess(self.h,self.f,n,-m,-q,self.fck,self.fcd,1.5,500,self.fyd)
        np.testing.assert_allclose(a['util'],b['util'],rtol=1e-9)
        np.testing.assert_allclose(a['As_req_X+'],b['As_req_X-'],rtol=1e-8)
    def test_steel_overload_not_hidden(self):
        r=assess(self.h,self.f,[[5000,0,0]],[[0,0,0]],[[0,0]],self.fck,self.fcd,1.5,500,self.fyd)
        self.assertGreater(r['steel_util'][0],1);self.assertIn('não satisfeito',r['status'][0])
    def test_missing_q_and_scope(self):
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',wk_check_enabled=True,axial_convention='Tracção positiva');d.sandwich_design=True
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,nxx=-20,nyy=-30,nxy=3,mxx=1,myy=2,mxy=.5,qxx=3) for c in [101,302]]))
        r=d.design_dataframe(df)
        self.assertEqual(r.loc[r.Combo_type.eq('ELU'),'Sand_status'].iloc[0],'Dados insuficientes')
        self.assertTrue(r.loc[r.Combo_type.eq('ELS-QP'),'wk_max_mm'].isna().all())
        self.assertFalse(any(c.startswith('Phys') for c in r));self.assertEqual(WallsEC2App.panel_outcome(r)[0],'Incompleto')
    def test_vectorized_against_single_rows(self):
        rng=np.random.default_rng(81);n=rng.uniform(-100,100,(10,3));m=rng.uniform(-5,5,(10,3));q=rng.uniform(-20,20,(10,2));r=assess(self.h,self.f,n,m,q,self.fck,self.fcd,1.5,500,self.fyd)
        for i in range(len(n)):
            s=assess(self.h,self.f,n[i:i+1],m[i:i+1],q[i:i+1],self.fck,self.fcd,1.5,500,self.fyd)
            self.assertAlmostEqual(r['util'][i],s['util'][0],places=7)
