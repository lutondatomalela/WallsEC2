import math,unittest
import numpy as np
import pandas as pd
from WallsEC2 import WallDesigner, RebarSolution, WallsEC2App, clean_dataframe
from wall_shear_design import required_longitudinal_area, shear_reinforcement_trial, refine_directional_shear_mesh

class Audit194(unittest.TestCase):
    def designer(self,h=220,**kw):
        p=dict(thickness_mm=h,cover_mm=30,concrete_class='C30/37',fyk=500,phi_min_mm=10,phi_max_mm=20,axial_convention='Tracção positiva',elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',wk_check_enabled=True,optimize_rebar=True,base_horizontal_phi=12,base_vertical_phi=12)
        p.update(kw);return WallDesigner(**p)
    def test_heavy_mesh_qp_no_elu_failure(self):
        d=self.designer();a=d.rebar_from_phi_spacing(12,100);b=RebarSolution(20,200,math.pi*(12**2+2*20**2)/4*5,text_override='Ø12//200 + 2Ø20//200');self.assertEqual(d.mrd_kNm_per_m(b.as_prov,b.phi),0.)
        data=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,mxx=1,myy=2,mxy=1,nxx=-10,nyy=10,nxy=1,qxx=10,qyy=10) for c in (302,303,311)]))
        for _,r in data.iterrows():
            v=d.design_one(r,[a,a,b,b]);self.assertTrue(math.isnan(v['util_M']));self.assertTrue(math.isnan(v['util_Qx']));self.assertNotEqual(v['Status'],'Não conforme');self.assertNotIn('utilização à flexão superior',v['Verification_reason'])
    def test_actual_depth_families(self):
        d=self.designer(250);a=RebarSolution(20,200,math.pi*(12**2+20**2)/4*5,text_override='Ø12//200 + Ø20//200');b=d.rebar_from_phi_spacing(12,200)
        self.assertAlmostEqual(d.shear_face_depth(a,b,True),220-(144*6+400*10)/544)
        self.assertAlmostEqual(d.shear_face_depth(b,a,False),194.)
    def test_inverse_shear(self):
        d=self.designer();depth=180.;sigma=-.5;v=d.shear_vrdc_kN_per_m(2000,depth,sigma)
        self.assertAlmostEqual(float(required_longitudinal_area(v,depth,sigma,d.fck,d.cp['fcd'],d.gamma_c)),2000.)
        self.assertTrue(math.isinf(float(required_longitudinal_area(1e4,depth,sigma,d.fck,d.cp['fcd'],d.gamma_c))))
        self.assertEqual(float(required_longitudinal_area(5,depth,0,d.fck,d.cp['fcd'],d.gamma_c)),0.)
    def test_trial_not_credit(self):
        d=self.designer();r=shear_reinforcement_trial(160,90,180,30,20,500,d.fyd)
        self.assertAlmostEqual(r['asw_mm2_m2'],160*1e6/(.9*180*d.fyd));self.assertEqual(r['delta_ftd_kN_m'],80)
        self.assertAlmostEqual(r['vrdmax_kN_m'],.9*180*.6*(1-30/250)*20/2)
        self.assertIn('pormenorizar',r['status'])
    def test_directional_refinement_and_no_credit(self):
        d=self.designer(250);a=d.rebar_from_phi_spacing(12,200);g=pd.DataFrame(dict(Panel=['1'],shear_ok=[True],NXX=[0.],NYY=[0.],QXX=[0.],QYY=[125.]));adopted={'1':[a,a,a,a]};refine_directional_shear_mesh(d,g,adopted);m=adopted['1'];self.assertGreater(m[2].as_prov,a.as_prov);self.assertGreater(m[3].as_prov,a.as_prov)
        r=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=101,mxx=0,myy=1,mxy=0,nxx=0,nyy=0,nxy=0,qxx=0,qyy=125)])).iloc[0];v=d.design_one(r,m);self.assertLessEqual(v['util_Qy'],1+1e-8)
    def test_missing_shear_does_not_claim_pass(self):
        self.assertTrue(math.isnan(shear_reinforcement_trial(0,1,100,30,20,500,435,missing=True)['asw_mm2_m2']))
if __name__=='__main__':unittest.main()

class WoodArmerAudit(unittest.TestCase):
    def test_optimized_orthogonal_equilibrium(self):
        d=WallDesigner(250,30,'C30/37',500,wood_armer_method='Wood-Armer optimizado')
        rng=np.random.default_rng(194)
        for a,b,c in rng.normal(size=(1000,3))*50:
            xp,xn,yp,yn,_=d.wood_armer_moments(a,b,c)
            for x,y,m in ((xp,yp,np.array([[a,c],[c,b]])),(xn,yn,-np.array([[a,c],[c,b]]))):
                self.assertGreaterEqual(min(x,y),0);self.assertGreaterEqual(np.linalg.eigvalsh(np.diag([x,y])-m).min(),-1e-9)
                self.assertLessEqual(x+y,max(m[0,0]+abs(c),0)+max(m[1,1]+abs(c),0)+1e-9)
    def test_zero_cross_term_does_not_copy_principal(self):
        d=WallDesigner(250,30,'C30/37',500,wood_armer_method='Wood-Armer optimizado')
        self.assertEqual(d.wood_armer_moments(50,0,0)[:4],(50,0,0,0))
    def test_failed_service_trace(self):
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',axial_convention='Tracção positiva',wk_check_enabled=True)
        rr=d.design_dataframe(clean_dataframe(pd.DataFrame([dict(panel=1,node=5,case=101,mxx=1,myy=1,mxy=0,nxx=0,nyy=0,nxy=0,qxx=0,qyy=0),dict(panel=1,node=6,case=302,mxx=1,myy=1,mxy=0,nxx=0,nyy=0,nxy=0,qxx=0,qyy=0)])))
        rr.loc[rr.Combo_type.eq('ELS-QP'),['Status','Verification_reason']]=['Não conforme','Falha de ensaio ELS']
        outcome,reason=WallsEC2App.panel_outcome(rr);self.assertEqual(outcome,'Não conforme');self.assertIn('nó 6',reason);self.assertIn('302',reason);self.assertIn('Falha de ensaio ELS',reason)
