import unittest
import numpy as np
from wall_physical_layers import PhysicalCapacity, layout
from wall_concrete_fibres import net_slices, net_fibre_geometry
from wall_shell_service import solve_cracked_shell

class NetCentroids(unittest.TestCase):
    def setUp(self):
        self.h=250.;self.f=layout(self.h,30,[[(1,12,200),(1,20,200)],[(1,12,200)],[(1,16,150)],[(1,12,200)]])
    def test_exact_area_and_first_moment(self):
        for k in (8,24,48,192):
            w,z=net_fibre_geometry(self.h,self.f,k)
            self.assertAlmostEqual(w.sum(),1-sum(f.bar.area_mm2_m for f in self.f)/(1000*self.h),places=12)
            self.assertAlmostEqual(w@z,-sum(f.bar.area_mm2_m*f.bar.z_mm for f in self.f)*2/(1000*self.h**2),places=12)
    def test_band_exact_resultant(self):
        h=self.h;plus,minus=.5,.3;fc=10.
        p=PhysicalCapacity(h,self.f,435,fc,net_area=True,band_fractions=(plus,minus),subdivisions=6)
        gross_first=h*h*(plus*(1-plus)-minus*(1-minus))/2
        expected_first=gross_first-sum(f.bar.area_mm2_m*f.bar.z_mm/1000 for f in self.f)
        self.assertAlmostEqual(np.dot(p.cap,p.centers)/fc,expected_first,places=9)
        self.assertAlmostEqual(p.check([-sum(p.cap),0,0],[-fc*expected_first/1000,0,0])[0],1.,places=8)
    def test_uniform_compression_exact_resultants(self):
        h=self.h;ec=30000.;es=200000.;eps=-.0002
        bars=[f.bar for f in self.f];a=sum(b.area_mm2_m/1000 for b in bars);first=sum(b.area_mm2_m*b.z_mm/1000 for b in bars)
        n=[ec*eps*(h-a)+es*eps*sum(b.area_mm2_m/1000 for b in bars if b.axis==i) for i in (0,1)]+[0.]
        m=[(-ec*eps*first+es*eps*sum(b.area_mm2_m*b.z_mm/1000 for b in bars if b.axis==i))/1000 for i in (0,1)]+[0.]
        w,z=net_fibre_geometry(h,self.f,48)
        s=solve_cracked_shell(h,n,m,bars,ec,concrete_weights=w,concrete_positions=z)
        self.assertIsNotNone(s);np.testing.assert_allclose(s.mid_strain,[eps,eps,0],atol=1e-10)
        np.testing.assert_allclose(s.curvature_per_mm,[0,0,0],atol=1e-11)
    def test_reflection(self):
        h=self.h;w,z=net_fibre_geometry(h,self.f,48)
        from dataclasses import replace
        ref=[replace(f,bar=replace(f.bar,z_mm=-f.bar.z_mm)) for f in self.f]
        wr,zr=net_fibre_geometry(h,ref,48)
        np.testing.assert_allclose(w,wr[::-1],atol=1e-14);np.testing.assert_allclose(z,-zr[::-1],atol=1e-14)
    def test_invalid_slices(self):
        with self.assertRaises(ValueError):net_slices(self.h,[],[0,1],[10,10])
        with self.assertRaises(ValueError):net_slices(self.h,self.f,[0],[20])
    def test_invalid_positions(self):
        with self.assertRaises(ValueError):solve_cracked_shell(250,[0,0,0],[0,0,0],[],30000,concrete_positions=np.zeros(48))
