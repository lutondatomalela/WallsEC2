import unittest
import numpy as np
from wall_sandwich_design import yielded_steel, demonstrated_steel, compression_limit, face_opt, solve_faces, layers
from wall_physical_layers import layout

class YieldFields(unittest.TestCase):
    def test_exact_yield_and_equilibrium(self):
        f=np.array([[0.,0.,100.]])
        # X at 125, Y at 80; q^2=125*80, exact rank-one concrete tensor.
        a=np.array([.3125,.5]);s,valid=yielded_steel(f,a,400,0)
        self.assertTrue(valid[0]);np.testing.assert_allclose(s,[[125,80]])
        c=f.copy();c[:,:2]-=s
        self.assertAlmostEqual(c[0,0]*c[0,1]-c[0,2]**2,0.)
        self.assertAlmostEqual(s[0,0]/a[0],400.)
        self.assertTrue(np.all(s>=.5*face_opt(f)));self.assertTrue(np.all(s<=2*face_opt(f)))
    def test_infeasible_bounds_or_other_yield(self):
        f=np.array([[0.,0.,100.],[0.,0.,100.],[10.,0.,0.]])
        _,valid=yielded_steel(f,np.array([.75,.5]),400,0);self.assertFalse(valid.any())
        _,valid=yielded_steel(f[:1],np.array([.3125,.15]),400,0);self.assertFalse(valid[0])
    def test_angle_limit_not_bypassed(self):
        f=np.array([[0.,0.,100.]])
        a=np.array([.3125,.5]);s,_=yielded_steel(f,a,400,0)
        # Actual yield and small angle.
        _,u,ok,ang,lim,rule,_=compression_limit(f,s,100,30,20,400,a,np.array([[0.,0.,1.]]))
        self.assertTrue(ok[0]);self.assertLess(ang[0],15);self.assertEqual(rule[0],'6.112 + F.1')
        # Elastic principal axis is perpendicular to compression direction.
        _,_,_,ang,_,rule,_=compression_limit(f,s,100,30,20,400,a,np.array([[0.,0.,-1.]]))
        self.assertGreater(ang[0],15);self.assertIn('não demonstrado',rule[0])
    def test_coupled_exact_residual(self):
        f=layout(250,30,[[(1,12,200)]]*4);ls=layers(250,f,(70.,80.))
        n=np.array([[50.,-10.,60.]]);m=np.array([[3.,-2.,1.]])
        r=solve_faces(n,m,ls,30,20,500/1.15,align=True,yield_search=True,detail=True)
        self.assertTrue(r[4][0]);self.assertLess(r[3][0],1e-7);np.testing.assert_allclose(r[5]+r[6],n)

class SecondOrderCoverage(unittest.TestCase):
    def test_known_strip_status(self):
        from wall_sandwich_design import strip_allowance_status
        status=strip_allowance_status(['Não requerida (N ≤ 0)','Dispensada','Incluída'],['Não requerida (N ≤ 0)']*3,[True,True,True])
        self.assertTrue(status[0].startswith('Dispensada'));self.assertTrue(status[1].startswith('Dispensada'));self.assertTrue(status[2].startswith('Incluída'))
    def test_missing_local_stability_not_promoted(self):
        from wall_sandwich_design import strip_allowance_status
        status=strip_allowance_status(['Pendente: l0','Dispensada','Instável'],['Não requerida (N ≤ 0)']*3,[False,False,True])
        self.assertTrue(np.all(status=='Dados locais pendentes'))
