import math, unittest
import numpy as np
from shell_crack_detail import principal_relative_strain
from wall_physical_layers import crack_candidate,layout

class InclinedRelativeStrain(unittest.TestCase):
    def test_no_shear(self):
        self.assertAlmostEqual(principal_relative_strain(.001,.002,0),.002)
        self.assertEqual(principal_relative_strain(-.001,-.002,0),0)
    def test_equal_biaxial(self):
        self.assertAlmostEqual(principal_relative_strain(.001,.001,.002),.002)
    def test_engineering_shear_and_reflection(self):
        self.assertAlmostEqual(principal_relative_strain(0,0,.002),.001)
        self.assertEqual(principal_relative_strain(.001,.002,-.003),principal_relative_strain(.002,.001,.003))
    def test_eigenvalue_reference(self):
        for x,y,g in np.random.default_rng(2026).normal(0,.001,(1000,3)):
            self.assertAlmostEqual(principal_relative_strain(x,y,g),max(0.,np.linalg.eigvalsh([[x,g/2],[g/2,y]])[-1]),places=14)
    def test_invalid(self):
        with self.assertRaises(ValueError):principal_relative_strain(0,math.nan,0)
    def test_hybrid_diagnostic_not_wk(self):
        fam=layout(250,30,[[(1,12,100)]]*4)
        r=crack_candidate(250,fam,[50,50,60],[0,0,0],30000,2.9,fyk=500)
        for side in ('plus','minus'):
            self.assertGreaterEqual(r['PhysQP_Tan31_candidate_'+side+'_mm'],r['PhysQP_candidate_'+side+'_mm'])
        self.assertIn('wk pendente',r['PhysQP_status']);self.assertNotIn('wk_max_mm',r)
