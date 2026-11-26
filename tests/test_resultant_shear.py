import unittest
import numpy as np
from wall_resultant_shear import resultant_shear
from wall_physical_layers import layout
from WallsEC2 import WallDesigner

class TestResultantShear(unittest.TestCase):
    def setUp(self):
        self.f=layout(220,30,[[(1,12,200)]]*4)
        self.d=WallDesigner(220,30,'C30/37',500)
    def screen(self,n,q):
        return resultant_shear(220,self.f,np.atleast_2d(n),np.atleast_2d(q),30,20,1.5)
    def test_axis_reference(self):
        r=self.screen([0,0,0],[0,100]); d=184.;a=1000*np.pi*12**2/(4*200)
        self.assertAlmostEqual(r['PhysShear_d_mm'][0],d)
        self.assertAlmostEqual(r['PhysShear_VRdc_kN_m'][0],self.d.shear_vrdc_kN_per_m(a,d))
    def test_resultant_and_rho(self):
        r=self.screen([0,0,0],[30,40]);a=1000*np.pi*12**2/(4*200)
        self.assertAlmostEqual(r['PhysShear_VEd_kN_m'][0],50)
        self.assertAlmostEqual(r['PhysShear_rho'][0],.36*a/(1000*172)+.64*a/(1000*184))
    def test_reflection(self):
        a=self.screen([150,-50,80],[30,40]);b=self.screen([150,-50,-80],[-30,40]);np.testing.assert_allclose(a['PhysShear_util'],b['PhysShear_util'])
    def test_tension_penalty_no_compression_credit(self):
        a=self.screen([0,0,0],[100,0]);b=self.screen([200,0,0],[100,0]);c=self.screen([-200,0,0],[100,0])
        self.assertGreater(b['PhysShear_util'][0],a['PhysShear_util'][0]);self.assertEqual(a['PhysShear_util'][0],c['PhysShear_util'][0])
    def test_missing_zero(self):
        r=self.screen([[0,0,0],[0,0,0]],[[0,0],[np.nan,0]])
        self.assertEqual(r['PhysShear_util'][0],0);self.assertTrue(np.isnan(r['PhysShear_util'][1]));self.assertEqual(r['PhysShear_status'][1],'Dados insuficientes')
    def test_combined_can_exceed_axis(self):
        r=self.screen([[0,0,0]]*3,[[80,0],[0,80],[80,80]])
        self.assertGreater(r['PhysShear_util'][2],max(r['PhysShear_util'][:2]))
