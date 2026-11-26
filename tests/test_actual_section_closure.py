import math
import unittest
import numpy as np
from wall_section import Section,nominal_stiffness
from WallsEC2 import WallDesigner,clean_dataframe
import pandas as pd

class ActualSectionClosure(unittest.TestCase):
    def test_independent_uniform_tension_with_distinct_layers(self):
        layers=((84.,400.),(80.,200.),(-82.,300.),(-76.,500.))
        sec=Section(250,49,600,800,layers=layers)
        n,m=sec.response(-.01,-.01)
        self.assertAlmostEqual(n,-1400*sec.fyd/1000,places=10)
        self.assertAlmostEqual(m,sec.fyd*sum(z*a for z,a in layers)/1e6,places=10)
    def test_profiles_respect_actual_steel_and_concrete_limits(self):
        sec=Section(250,49,600,800,layers=((84.,400.),(80.,200.),(-82.,300.),(-76.,500.)))
        profiles=sec.strain_profiles(160)
        z,a=np.array(sec.steel_geometry).T
        eps=profiles.mean(axis=1)[:,None]+np.diff(profiles,axis=1)*z/sec.h
        self.assertGreaterEqual(eps.min(),-sec.eps_ud-1e-13)
        self.assertLessEqual(profiles.max(),sec.eps_cu+1e-13)
        # Surface tension may exceed steel tensile strain: correct domain.
        self.assertLess(profiles.min(),-sec.eps_ud)
        self.assertTrue(np.allclose(eps[:160,0],-sec.eps_ud))
    def test_asymmetric_reflection(self):
        layers=((84.,400.),(80.,200.),(-82.,300.),(-76.,500.))
        a=Section(250,49,600,800,layers=layers)
        b=Section(250,49,800,600,layers=tuple((-z,v) for z,v in layers))
        for n in (-300.,0.,500.,1000.):
            ma=a.moment_bounds(n);mb=b.moment_bounds(n)
            np.testing.assert_allclose(ma,[-mb[1],-mb[0]],rtol=1e-10,atol=1e-10)
    def test_service_pure_tension_independent_linear_equilibrium(self):
        layers=((84.,400.),(80.,200.),(-82.,300.),(-76.,500.))
        sec=Section(250,49,600,800,layers=layers)
        z,area=np.array(layers).T
        B=np.column_stack([np.ones(len(z)),-z]); K=B.T@(sec.es*area[:,None]*B)
        n,m=-200.,5.;x=np.linalg.solve(K,[n*1000,m*1e6]);expected=sec.es*(B@x)
        self.assertTrue((expected<0).all())
        r=sec.service(n,m)
        np.testing.assert_allclose(r['sigma_layers'],expected,rtol=1e-10,atol=1e-10)
    def test_actual_inertia(self):
        d=WallDesigner(250,30,'C30/37',500,phi_max_mm=20)
        a=d.rebar_from_phi_spacing(12,200);b=d.rebar_from_phi_spacing(20,200)
        x=d.section_for(a,b,'X',(b,a));y=d.section_for(b,a,'Y',(a,b))
        self.assertAlmostEqual(x.steel_geometry[0][0],69.)
        self.assertAlmostEqual(x.steel_geometry[1][0],-73.)
        self.assertAlmostEqual(y.steel_geometry[0][0],85.)
        self.assertAlmostEqual(y.steel_geometry[1][0],-89.)
        self.assertAlmostEqual(y.steel_inertia,b.as_prov*85**2+a.as_prov*89**2)
        kw=dict(n_kn=300,m0_knm=30,h=250,as_total=a.as_prov+b.as_prov,axis_cover=40,fck=30,fcd=20,fyd=435,l0_mm=3000,phi_eff=1.5)
        r=nominal_stiffness(**kw,steel_inertia=y.steel_inertia)
        lam=3000/(250/math.sqrt(12));kc=math.sqrt(30/20)*min((300/(250*20))*lam/170,.2)/2.5
        ei=kc*(22000*3.8**.3/1.2)*1000*250**3/12+200000*y.steel_inertia
        self.assertAlmostEqual(r['buckling_load'],math.pi**2*ei/3000**2/1000)
    def test_tensile_surface_without_tensile_steel_is_pending(self):
        sec=Section(200,44,1000,1000)
        found=False
        for n in (500.,1000.,1500.):
            for m in np.linspace(0,100,101):
                r=sec.cracking(n,m,12,150,12,150)
                st=r['service'];ext=-st['eps0']+st['curvature']*100
                if ext>1e-10 and st['sigma_plus']>=0:
                    self.assertTrue(math.isnan(r['plus']['wk']));found=True;break
            if found:break
        self.assertTrue(found)
    def test_mixed_area_guard(self):
        with self.assertRaises(ValueError):Section(250,30,600,800,layers=((84.,500.),(-82.,800.)))
    def test_rejected_base_not_counted_in_crack_spacing(self):
        from WallsEC2 import RebarSolution
        d=WallDesigner(250,30,'C30/37',500)
        a=RebarSolution(12,200,565.486677646,base_text='Ø20//400',add_text='Ø12//200')
        self.assertEqual(d.rebar_crack_geometry(a),(12.,200.,1))
    def test_intercalated_can_exceed_direct_candidate_limit(self):
        d=WallDesigner(250,30,'C30/37',500,optimize_rebar=True,phi_min_mm=12,phi_max_mm=12,base_vertical_phi=12,base_vertical_spacing=200)
        d.spacing_candidates=[200.]
        r=d.optimize_rebar_solution(1000,200,True,'Y+')
        self.assertGreaterEqual(r.as_prov,1000)
        self.assertIn('Ø12//200 +',r.text)
    def test_partial_crack_never_approved(self):
        d=WallDesigner(250,30,'C30/37',500,wk_check_enabled=True,qp_case='302')
        self.assertEqual(d.crack_full_status([0.,0.,0.,math.nan],302)[0],'Não avaliado')
        self.assertEqual(d.crack_full_status([0.,.31,0.,math.nan],302)[0],'Verificar')
