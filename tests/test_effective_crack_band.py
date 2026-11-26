import math
import unittest
from wall_section import Section
from WallsEC2 import WallDesigner, RebarSolution

class EffectiveCrackBandTests(unittest.TestCase):
    def setUp(self):
        self.sec=Section(250,40,1200,1000,layers=((90.,600.),(60.,600.),(-90.,1000.)))
        self.details=((12,200,1),(16,150,1),(16,150,1))
    def test_only_effective_family_credited(self):
        r=self.sec.cracking(100,10,16,150,16,150,family_details=self.details)['plus']
        self.assertTrue(math.isfinite(r['wk']))
        self.assertGreater(r['hc_eff'],35.)
        self.assertLess(r['hc_eff'],65.)
        self.assertEqual(r['as_eff'],600.)
        self.assertAlmostEqual(r['rho_eff'],600/(1000*r['hc_eff']))
        self.assertEqual(r['phi_eff'],12.)
        self.assertEqual(r['spacing_eff'],200.)
    def test_unresolved_mixed_family_is_pending(self):
        r=self.sec.cracking(100,10,16,150,16,150)['plus']
        self.assertTrue(math.isnan(r['wk']))
        self.assertIn('famílias eficazes',r['reason'])
    def test_invalid_family_detail_rejected(self):
        with self.assertRaises(ValueError):
            self.sec.cracking(100,10,16,150,16,150,family_details=((12,0,1),))
    def test_unequal_spacing_no_unverified_intercalation_credit(self):
        d=WallDesigner(250,30,'C30/37',500)
        sol=RebarSolution(12,200,1200,text_override='Ø12//200 + Ø16//300')
        # RebarSolution.text is computed from accepted adopted description.
        self.assertEqual(d.rebar_crack_geometry(sol)[1],300.)
    def test_unverified_intercalation_not_credited_in_direct_wk(self):
        r=self.sec.cracking(-300,0,16,75,16,150,family_details=self.details)['plus']
        self.assertEqual(r['as_eff'],1200.)
        self.assertEqual(r['spacing_eff'],200.)
