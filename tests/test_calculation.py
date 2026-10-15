import math
import unittest
import pandas as pd
from WallsEC2 import (WallDesigner, RebarSolution, clean_dataframe,
                      reduce_to_governing_cases, moment_unit_factor_to_kNm_per_m,
                      shear_unit_factor_to_kN_per_m)


def designer(**kw):
    args = dict(thickness_mm=200, cover_mm=30, concrete_class='C30/37', fyk=500)
    args.update(kw)
    return WallDesigner(**args)


class CalculationTests(unittest.TestCase):
    def test_materials(self):
        d = designer()
        self.assertAlmostEqual(d.cp['fcd'], 20)
        self.assertAlmostEqual(d.fyd, 500/1.15)

    def test_bad_geometry(self):
        for kw in [dict(thickness_mm=0), dict(cover_mm=-1), dict(cover_mm=95),
                   dict(gamma_c=0), dict(fyk=float('inf')), dict(concrete_class='abc'),
                   dict(phi_min_mm=30, phi_max_mm=32), dict(aggregate_mm=-1)]:
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                designer(**kw)

    def test_units(self):
        for unit, factor in [('kNm/m',1), ('Nmm/mm',.001), ('Nm/m',.001), ('kNmm/m',.001)]:
            self.assertEqual(moment_unit_factor_to_kNm_per_m(unit), factor)
        for unit, factor in [('kN/m',1), ('N/mm',1), ('N/m',.001)]:
            self.assertEqual(shear_unit_factor_to_kN_per_m(unit), factor)
        with self.assertRaises(ValueError):
            moment_unit_factor_to_kNm_per_m('kg')

    def test_invalid_values_not_zero(self):
        for value in ['oops', '', float('inf'), float('nan')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                clean_dataframe(pd.DataFrame([dict(MXX=value)]))

    def test_decimal_comma(self):
        df = clean_dataframe(pd.DataFrame([dict(MXX='1.234,56')]))
        self.assertAlmostEqual(df.iloc[0].mxx,1234.56)

    def test_no_unsafe_case_reduction(self):
        df = clean_dataframe(pd.DataFrame([dict(panel=1,case=i,mxx=i,myy=-i,mxy=i) for i in range(10)]))
        self.assertEqual(len(reduce_to_governing_cases(df)),10)

    def test_wa(self):
        self.assertEqual(designer().wood_armer_moments(10,-5,3)[:4],(13,0,0,8))
        self.assertEqual(designer().wood_armer_moments(0,0,-5)[:4],(5,5,5,5))

    def test_exact_flexure_equilibrium(self):
        d = designer()
        m = 20
        a = d.flexural_as_required(m)
        self.assertAlmostEqual(d.mrd_kNm_per_m(a,max(d.phi_candidates)),m,places=9)
        self.assertEqual(d.mrd_kNm_per_m(20000,16),0)

    def test_no_forced_rebar(self):
        with self.assertRaises(ValueError):
            designer().choose_rebar(100000)
        with self.assertRaises(ValueError):
            designer().choose_compatible_additional_rebar(100000,RebarSolution(10,100,785),400)

    def test_shear_hand_calculation(self):
        d=designer(gamma_c=1.8)
        a,depth=1000,150
        k=2
        rho=a/(1000*depth)
        expected=max(.18/1.8*k*(100*rho*30)**(1/3),.035*k**1.5*math.sqrt(30))*depth
        self.assertAlmostEqual(d.shear_vrdc_kN_per_m(a,depth),expected)
        self.assertLess(d.shear_vrdc_kN_per_m(a,depth),designer().shear_vrdc_kN_per_m(a,depth))
        self.assertAlmostEqual(d.shear_vrdc_kN_per_m(30000,depth),d.shear_vrdc_kN_per_m(3000,depth))

    def test_crack_hand_calculation(self):
        d=designer(wk_check_enabled=True,qp_case='203')
        sol=RebarSolution(12,150,math.pi*12**2/4*1000/150)
        wk,sigma,sr,_=d.crack_width_estimate(20,sol)
        depth=200-30-16-6
        alpha=200000/(22000*(3.8)**.3)
        na=alpha*sol.as_prov/1000
        x=math.sqrt(na**2+2*na*depth)-na
        expected_sigma=20e6/((depth-x/3)*sol.as_prov)
        h=min(2.5*(200-depth),(200-x)/3,100)
        rho=sol.as_prov/(1000*h)
        expected_sr=3.4*30+.8*.5*.425*12/rho
        eps=max((expected_sigma-.4*d.cp['fctm']/rho*(1+alpha*rho))/200000,.6*expected_sigma/200000)
        self.assertAlmostEqual(sigma,expected_sigma)
        self.assertAlmostEqual(sr,expected_sr)
        self.assertAlmostEqual(wk,expected_sr*eps)

    def test_crack_stress_not_clipped(self):
        sol=RebarSolution(8,200,251.3)
        d=designer(wk_check_enabled=True)
        self.assertGreater(d.crack_width_estimate(100,sol)[1],500)
        self.assertEqual(d.crack_check_detail(100,sol,'+','X')['Status'],'Verificar')

    def test_large_spacing_cracks(self):
        d=designer()
        sol=RebarSolution(12,400,282.7)
        sr=d.crack_width_estimate(10,sol)[2]
        alpha=200000/(22000*3.8**.3)
        na=alpha*sol.as_prov/1000
        depth=d.effective_depth(12)
        x=math.sqrt(na**2+2*na*depth)-na
        self.assertAlmostEqual(sr,1.3*(200-x))

    def test_equivalent_diameter(self):
        sol=RebarSolution(12,200,0,text_override='Ø10//200 + Ø12//200')
        phi,spacing,n=designer().rebar_crack_geometry(sol)
        self.assertAlmostEqual(phi,(100+144)/(10+12))
        self.assertEqual(spacing,100)
        self.assertEqual(n,2)

    def test_partial_wa_rejected(self):
        row=clean_dataframe(pd.DataFrame([{'MXX+':10}])).iloc[0]
        with self.assertRaises(ValueError):
            designer().design_one(row)

    def test_missing_shear_prevents_ok(self):
        row=clean_dataframe(pd.DataFrame([dict(mxx=5,myy=5,mxy=0)])).iloc[0]
        self.assertEqual(designer().design_one(row)['Status'],'Verificar')

    def test_membrane_prevents_ok_and_converts(self):
        row=clean_dataframe(pd.DataFrame([dict(mxx=5,myy=5,mxy=0,qxx=0,qyy=0,nyy=10000)])).iloc[0]
        r=designer(shear_unit='N/m').design_one(row)
        self.assertEqual(r['NYY_kN_m'],10)
        self.assertEqual(r['Status'],'Verificar')

    def test_wk_only_qp(self):
        row=clean_dataframe(pd.DataFrame([dict(case=101,mxx=5,myy=5,mxy=0,qxx=0,qyy=0)])).iloc[0]
        r=designer(wk_check_enabled=True,qp_case='203').design_one(row)
        self.assertTrue(math.isnan(r['wk_max_mm']))
        self.assertEqual(r['Status'],'Verificar')

    def test_crack_k_interpolation(self):
        d=designer(thickness_mm=550)
        expected=.4*.825*d.cp['fctm']*1000*550/2/500
        self.assertAlmostEqual(d.crack_min_as_per_face(),expected)

    def test_axis_swap(self):
        row=clean_dataframe(pd.DataFrame([dict(case=101,mxx=5,myy=10,mxy=2,qxx=1,qyy=2)])).iloc[0]
        a=designer().design_one(row)
        b=designer(swap_local_axes=True).design_one(row)
        self.assertEqual(a['Mx+_WA'],b['My+_WA'])

    def test_common_panel_mesh_elu_els(self):
        df=clean_dataframe(pd.DataFrame([
            dict(panel=1,node=1,case=101,mxx=25,myy=5,mxy=0,qxx=1,qyy=1),
            dict(panel=1,node=2,case=203,mxx=10,myy=3,mxy=0,qxx=1,qyy=1)]))
        d=designer(wk_check_enabled=True,qp_case='203')
        r=d.design_dataframe(df)
        self.assertEqual(r.iloc[0]['X+_rebar'],r.iloc[1]['X+_rebar'])
        self.assertEqual(r.iloc[0]['Asx+_prov_mm2_m'],r.iloc[1]['Asx+_prov_mm2_m'])
        self.assertTrue(math.isfinite(r.iloc[1]['wk_max_mm']))

    def test_missing_qp_rejected(self):
        df=clean_dataframe(pd.DataFrame([dict(panel=1,case=101,mxx=5)]))
        with self.assertRaises(ValueError):
            designer(wk_check_enabled=True,qp_case='203').design_dataframe(df)

if __name__=='__main__':
    unittest.main()
