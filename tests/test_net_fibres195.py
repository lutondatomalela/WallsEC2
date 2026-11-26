import unittest
import numpy as np
from wall_physical_layers import layout
from wall_concrete_fibres import net_weights
from wall_shell_service import solve_cracked_shell

class NetFibres(unittest.TestCase):
    def test_area_and_symmetry(self):
        h=220.;f=layout(h,30,[[(1,12,200),(1,16,200)]]*4)
        for nf in (24,48,96):
            w=net_weights(h,f,nf)
            self.assertAlmostEqual(w.sum(),1-sum(x.bar.area_mm2_m for x in f)/(1000*h),places=12)
            np.testing.assert_allclose(w,w[::-1],atol=1e-15)
            self.assertTrue(np.all(w>0))
    def test_compressive_shear_exact_net_area(self):
        h=220.;f=layout(h,30,[[(1,12,200)]]*4);w=net_weights(h,f)
        ec=30000.;s=solve_cracked_shell(h,[-1000,-1000,100],[0,0,0],[x.bar for x in f],ec,concrete_weights=w)
        self.assertIsNotNone(s);self.assertAlmostEqual(s.mid_strain[2],100/(h*w.sum()*ec),places=11)
        self.assertLess(s.residual_mpa,1e-7)
    def test_tension_unchanged(self):
        h=220.;f=layout(h,30,[[(1,12,200)]]*4);w=net_weights(h,f);bars=[x.bar for x in f]
        a=solve_cracked_shell(h,[100,150,0],[0,0,0],bars,30000.);b=solve_cracked_shell(h,[100,150,0],[0,0,0],bars,30000.,concrete_weights=w)
        np.testing.assert_allclose(a.steel_stress_mpa,b.steel_stress_mpa,atol=1e-5)
    def test_invalid_weights(self):
        with self.assertRaises(ValueError):solve_cracked_shell(220,[0,0,0],[0,0,0],[],30000,concrete_weights=np.ones(48))
