import unittest
import numpy as np
from wall_core_stress_field import reconstruct
from wall_asymmetric_core import AsymmetricCore
from wall_physical_layers import layout

class CoreStressFieldTests(unittest.TestCase):
    def test_exact_pure_shear(self):
        a=reconstruct([100,0],50,20,1.5,10,435,4000)
        self.assertTrue(a.valid);np.testing.assert_allclose(a.n,[-150,0,0],atol=1e-12)
        np.testing.assert_allclose(a.m,[-3,0,0],atol=1e-12);np.testing.assert_allclose(a.q,[100,0],atol=1e-12)
        self.assertAlmostEqual(a.nzz,0);self.assertAlmostEqual(a.strut_util,100/50*(1.5+1/1.5)/10)
        self.assertAlmostEqual(a.link_util,(100/1.5)*1e6/(50*435*4000))
    def test_rank_one_concrete_and_sign(self):
        a=reconstruct([-60,80],50,-25,2.,10,435,4000)
        self.assertTrue(a.valid);np.testing.assert_allclose(np.linalg.eigvalsh(a.concrete_mpa),[-5,0,0],atol=1e-12)
        np.testing.assert_allclose(a.n,[-72,-128,96],atol=1e-12);np.testing.assert_allclose(a.q,[-60,80],atol=1e-12)
    def test_capacity_guard(self):
        self.assertFalse(reconstruct([100,0],50,0,1.,10,435,0).valid)
        self.assertFalse(reconstruct([1000,0],50,0,1.,10,435,100000).valid)
        self.assertTrue(reconstruct([0,0],50,0,1.,10,435,0).valid)
    def test_explicit_truss_below_vrdc(self):
        model=AsymmetricCore(250,layout(250,30,[[(1,12,200)]]*4),30,20,500,435)
        n=[-200,-200,0];m=[1,2,0];q=[30,40]
        default=model.assess(n,m,q,200);trial=model.assess(n,m,q,200,force_links=True)
        self.assertEqual(default.asw_proposed,0);self.assertGreater(trial.asw_proposed,0)
        self.assertLessEqual(max(trial.face_util,trial.core_util,trial.link_util),1+1e-7)
        self.assertLess(trial.tensor_residual,1e-9)
    def test_no_spurious_links_for_zero_shear(self):
        model=AsymmetricCore(250,layout(250,30,[[(1,12,200)]]*4),30,20,500,435)
        self.assertEqual(model.assess([0,0,0],[0,0,0],[0,0],0,force_links=True).asw_proposed,0)
