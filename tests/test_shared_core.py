import unittest
import numpy as np
from wall_physical_layers import layout,PhysicalCapacity
from wall_shared_core import SharedCore,assess_layouts

class SharedCoreTests(unittest.TestCase):
    def setUp(self):
        self.f=layout(250,30,[[(1,12,200)]]*4)
        self.m=PhysicalCapacity(250,self.f,435,10,band_fractions=(.4,.4),subdivisions=3,net_area=True)
        self.c=SharedCore(self.m,30,500,10)
    def test_zero(self):
        r=self.c.assess([0,0,0],[0,0,0],[0,0]);self.assertEqual(r.util,0);self.assertEqual(r.asw_proposed,0)
    def test_shear_requires_proposed_ties(self):
        r=self.c.assess([-100,-100,0],[0,0,0],[80,60]);self.assertLessEqual(r.util,1);self.assertGreater(r.asw_required,0);self.assertGreaterEqual(r.asw_proposed,r.asw_required);self.assertLess(r.residual,1e-6);self.assertLessEqual(r.core_util,1)
    def test_core_shear_bound(self):
        # A uniaxial compressive stress has |tau_xz|<=sigma/2.
        # Even unlimited ties cannot carry Q above fc*core/2.
        r=self.c.assess([-1000,0,0],[0,0,0],[251,0]);self.assertIn('Sem equilíbrio',r.status)
    def test_compression_uses_core(self):
        r=self.c.assess([-2400,0,0],[0,0,0],[0,0]);self.assertLessEqual(r.util,1);self.assertEqual(r.asw_proposed,0);self.assertGreater(r.core_util,0)
    def test_reflection(self):
        a=self.c.assess([-200,-300,35],[10,20,3],[60,-20]);b=self.c.assess([-200,-300,35],[-10,-20,-3],[60,-20]);self.assertAlmostEqual(a.util,b.util,places=7);self.assertAlmostEqual(a.asw_required,b.asw_required,places=7)
    def test_rotation_90(self):
        a=self.c.assess([-200,-300,35],[10,20,3],[60,-20]);f=tuple(type(v)(v.label,v.phi,v.spacing,v.count,v.cover,type(v.bar)(1-v.bar.axis,v.bar.z_mm,v.bar.area_mm2_m)) for v in self.f);m=PhysicalCapacity(250,f,435,10,band_fractions=(.4,.4),subdivisions=3,net_area=True);b=SharedCore(m,30,500,10).assess([-300,-200,-35],[20,10,-3],[20,60]);self.assertAlmostEqual(a.util,b.util,places=7)
    def test_combined_budget(self):
        # A compression action close to the full-depth trace limit cannot
        # simultaneously reserve the same concrete for diagonal shear.
        r=self.c.assess([-2400,0,0],[0,0,0],[220,0]);self.assertIn('Sem equilíbrio',r.status)
    def test_layout_search(self):
        r=assess_layouts([self.m],[-100,-200,0],[0,0,0],[20,30],30,500,10);self.assertLess(r.util,1)
