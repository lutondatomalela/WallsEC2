import math
import unittest
import numpy as np
from wall_section import Section, nominal_stiffness
from WallsEC2 import WallDesigner, clean_dataframe, parse_case_set
import pandas as pd


def sec(**kw):
    args=dict(h=200,cover_axis=44,as_plus=1000,as_minus=1000)
    args.update(kw)
    return Section(**args)


class SectionTests(unittest.TestCase):
    def test_uniform_compression_exact(self):
        s=sec()
        n,m=s.response(.002,.002)
        expected=(20*(200000-2000)+400*2000)/1000
        self.assertAlmostEqual(n,expected)
        self.assertAlmostEqual(m,0)

    def test_uniform_tension_exact(self):
        s=sec()
        n,m=s.response(-.01,-.01)
        self.assertAlmostEqual(n,-2000*s.fyd/1000)
        self.assertAlmostEqual(m,0)

    def test_symmetry(self):
        s=sec()
        for a,b in [(.0035,-.004),(.0035,.001),(.001,-.002)]:
            n,m=s.response(a,b)
            nr,mr=s.response(b,a)
            self.assertAlmostEqual(n,nr)
            self.assertAlmostEqual(m,-mr)
        for n in [-500,0,1000,3000]:
            limits=s.moment_bounds(n)
            self.assertAlmostEqual(limits[0],-limits[1])

    def test_mesh_convergence(self):
        for n in [-500,0,500,2000,3500]:
            a=sec(fibres=160).moment_bounds(n,160)
            b=sec(fibres=320).moment_bounds(n,320)
            self.assertLess(abs(a[1]-b[1])/max(1,b[1]),.005)

    def test_axial_outside_domain(self):
        self.assertEqual(sec().check(10000,0)['status'],'Não conforme')
        self.assertEqual(sec().check(-2000,0)['status'],'Não conforme')

    def test_asymmetric_reversal(self):
        s=sec(as_plus=500,as_minus=1500)
        m=s.moment_bounds(0)
        self.assertGreater(-m[0],m[1])

    def test_asymmetric_pure_tension_requires_eccentricity(self):
        s=sec(as_plus=500,as_minus=1500)
        n,m=s.response(-.01,-.01)
        self.assertNotAlmostEqual(m,0)
        self.assertEqual(s.check(n,m)['status'],'OK')
        self.assertEqual(s.check(n,0)['status'],'Não conforme')

    def test_bending_limit(self):
        s=sec()
        limit=s.moment_bounds(0)[1]
        self.assertEqual(s.check(0,.9*limit)['status'],'OK')
        self.assertEqual(s.check(0,1.1*limit)['status'],'Não conforme')

    def test_service_tension_exact(self):
        s=sec()
        r=s.service(-200,0)
        self.assertAlmostEqual(r['sigma_plus'],-100)
        self.assertAlmostEqual(r['sigma_minus'],-100)
        self.assertEqual(r['concrete_max'],0)

    def test_service_compression_exact(self):
        s=sec()
        r=s.service(200,0)
        ec=22000*3.8**.3
        eps=200000/(ec*198000+200000*2000)
        self.assertAlmostEqual(r['sigma_plus'],200000*eps)
        self.assertAlmostEqual(r['concrete_max'],ec*eps)

    def test_service_equilibrium(self):
        for n in [-300,0,300,1000]:
            for m in [-30,0,30]:
                r=sec().service(n,m)
                self.assertLess(abs(r['residual_n']),.01)
                self.assertLess(abs(r['residual_m']),.01)

    def test_high_strength(self):
        for f in [50,60,80,90]:
            s=sec(fck=f,fcd=f/1.5)
            self.assertTrue(np.isfinite(s.interaction()).all())
            self.assertGreater(s.moment_bounds(0)[1],0)

    def test_nominal_stiffness_hand(self):
        r=nominal_stiffness(300,30,200,2000,44,30,20,500/1.15,3000,1.5)
        lam=3000/(200/math.sqrt(12))
        kc=math.sqrt(30/20)*min((300000/4000000)*lam/170,.2)/2.5
        ei=kc*(22000*3.8**.3/1.2)*1000*200**3/12+200000*2000*56**2
        nb=math.pi**2*ei/3000**2/1000
        amp=1+(math.pi**2/8)/(nb/300-1)
        self.assertAlmostEqual(r['buckling_load'],nb)
        self.assertAlmostEqual(r['moment'],30*amp)

    def test_instability(self):
        r=nominal_stiffness(1000,30,200,2000,44,30,20,500/1.15,10000)
        self.assertTrue(math.isinf(r['amplification']))

    def test_length_and_creep(self):
        kwargs=dict(n_kn=300,m0_knm=30,h=200,as_total=2000,axis_cover=44,fck=30,fcd=20,fyd=500/1.15,l0_mm=3000)
        a=nominal_stiffness(**kwargs)
        b=nominal_stiffness(**dict(kwargs,phi_eff=2))
        c=nominal_stiffness(**dict(kwargs,l0_mm=4000))
        self.assertGreater(b['amplification'],a['amplification'])
        self.assertGreater(c['amplification'],a['amplification'])

    def test_axial_stress_in_shear(self):
        d=WallDesigner(200,30,'C30/37',500)
        base=d.shear_vrdc_kN_per_m(1000,150)
        self.assertAlmostEqual(d.shear_vrdc_kN_per_m(1000,150,-1),base-.15*150)
        self.assertAlmostEqual(d.shear_vrdc_kN_per_m(1000,150,100),base+.15*4*150)
        self.assertEqual(d.shear_vrdc_kN_per_m(1000,150,-100),0)

    def test_case_ranges(self):
        self.assertEqual(parse_case_set('101-103 110;112'),{'101','102','103','110','112'})
        for text in ['103-101','abc','101-10000000']:
            with self.assertRaises(ValueError): parse_case_set(text)

    def test_selection_and_axial_sign(self):
        df=clean_dataframe(pd.DataFrame([
            dict(panel=1,node=1,case=c,mxx=10,myy=10,mxy=0,qxx=0,qyy=0,nxx=100,nyy=100,nxy=0)
            for c in [101,999]]))
        d=WallDesigner(200,30,'C30/37',500,elu_cases='101',axial_convention='Compressão positiva')
        r=d.design_dataframe(df)
        self.assertEqual(len(r),1)
        self.assertEqual(r.iloc[0]['Case'],101)
        self.assertTrue(math.isfinite(r.iloc[0]['NM_Y_util']))
        self.assertEqual(r.iloc[0]['Status'],'Verificar')

    def test_elu_qp_overlap(self):
        with self.assertRaises(ValueError):
            WallDesigner(200,30,'C30/37',500,elu_cases='101-203',qp_case='203')

    def test_invalid_section(self):
        for kw in [dict(cover_axis=100),dict(fibres=10),dict(eps_ud=.001),dict(h=float('nan'))]:
            with self.assertRaises(ValueError): sec(**kw)

if __name__=='__main__': unittest.main()
