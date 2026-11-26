"""Independent analytical checks for F and 6.109, not project calibration."""
import unittest
import numpy as np
from wall_sandwich_design import compression_limit, aligned_steel, face_opt, elastic_face, assess
from wall_physical_layers import layout

class CompressionTests(unittest.TestCase):
    fck=30.;fc=20.;fy=400.;nu=.528
    def calc(self,force,steel,elastic,area=(1.,1.),net=100.):
        return compression_limit(np.atleast_2d(force).astype(float),np.atleast_2d(steel).astype(float),net,self.fck,self.fc,self.fy,np.asarray(area),np.atleast_2d(elastic).astype(float))
    def test_biaxial_6110_and_F_cap(self):
        for a in (0.,.1,.2,.5,1.):
            _,u,ok,_,lim,rule,_=self.calc([-100,-100*a,0],[0,0],[-1,-a,0])
            expected=min(20.,17*(1+3.8*a)/(1+a)**2)
            self.assertAlmostEqual(lim[0],expected);self.assertAlmostEqual(u[0],1/expected);self.assertTrue(ok[0]);self.assertIn('6.110',rule[0])
    def test_aligned_6111_retains_F(self):
        # Pure shear: steel demands 100 kN/m each, compression principal -200.
        _,u,ok,ang,lim,rule,sr=self.calc([0,0,100],[100,100],[0,0,1]);self.assertTrue(ok[0]);self.assertAlmostEqual(ang[0],0.,places=5);self.assertAlmostEqual(sr[0],.25);self.assertAlmostEqual(lim[0],self.nu*self.fc);self.assertIn('6.111',rule[0])
    def test_6112_angular_domain(self):
        # Actual steel exactly at yield; plastic compressive direction 135 deg.
        for delta in (0.,10.,15.,16.,45.):
            a=np.deg2rad(135+delta);v=np.array([np.cos(a),np.sin(a)]);T=-np.outer(v,v);el=[T[0,0],T[1,1],T[0,1]]
            _,_,ok,ang,lim,rule,_=self.calc([0,0,100],[100,100],el,area=(.25,.25));self.assertTrue(ok[0]);self.assertAlmostEqual(ang[0],delta,places=5)
            if delta<=15:self.assertAlmostEqual(lim[0],self.nu*self.fc*(1-.032*delta));self.assertIn('6.112',rule[0])
            else:self.assertIn('não demonstrado',rule[0])
    def test_nonyield_offangle_not_6112(self):
        _,_,_,_,lim,rule,_=self.calc([0,0,100],[100,100],[-1,0,1]);self.assertIn('não demonstrado',rule[0]);self.assertAlmostEqual(lim[0],.52*self.nu*self.fc)
    def test_no_elastic_compression_not_certified(self):
        _,_,_,ang,_,rule,_=self.calc([0,0,100],[100,100],[2,2,1]);self.assertTrue(np.isnan(ang[0]));self.assertIn('não demonstrado',rule[0])
    def test_aligned_redistribution_and_bounds(self):
        q=np.array([[0.,0,100.],[-200,-10,100],[0,0,100]])
        # compression tensor rank one, direction cot=1.25, impossible direction for second row, too much for third.
        cot=np.array([1.25,1.,3.]);el=np.column_stack((-cot,-1/cot,np.ones(3)))
        demand=aligned_steel(q,el);np.testing.assert_allclose(demand[0],[125,80]);np.testing.assert_allclose(demand[1:],face_opt(q)[1:]);self.assertTrue(np.all(demand>=.5*face_opt(q)-1e-8));self.assertTrue(np.all(demand<=2*face_opt(q)+1e-8))
    def test_elastic_moment_units(self):
        n=np.array([[100,0,0.]]);m=np.array([[20,0,0.]])
        np.testing.assert_allclose(elastic_face(200.,n,m,50.),[[2,0,0]])
    def test_compression_trace_and_no_certification(self):
        f=layout(250,30,[[(1,12,200)]]*4);r=assess(250,f,[[0,0,100]],[[0,0,0]],[[0,0]],30,20,1.5,500,500/1.15)
        self.assertTrue(np.isfinite(r['util'][0]));self.assertIn('6.111',r['compression_rule_plus'][0]);self.assertAlmostEqual(r['angle_plus_deg'][0],0.,places=5)

    def test_prefer_documented_alternative_over_screen(self):
        f=layout(250,30,[[(1,12,200)]]*4)
        r=assess(250,f,[[20,50,80]],[[0,0,0]],[[0,0]],30,20,1.5,500,500/1.15)
        self.assertLess(r['util'][0],1.);self.assertIn('6.111',r['compression_rule_plus'][0]);self.assertIn('6.111',r['compression_rule_minus'][0])
    def test_pending_screen_not_reported_as_verified(self):
        f=layout(250,30,[[(1,12,200)]]*4)
        r=assess(250,f,[[-20,80,40]],[[0,0,0]],[[0,0]],30,20,1.5,500,500/1.15)
        self.assertLess(r['util'][0],1.);self.assertIn('6.109 não demonstrado',r['status'][0]);self.assertNotIn('Satisfeito no modelo',r['status'][0]);self.assertIn('continuidade por confirmar',r['transfer_status'][0])
