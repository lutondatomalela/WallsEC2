import unittest
import math
import pandas as pd
from WallsEC2 import WallDesigner, clean_dataframe, ec2_final_creep, WallsEC2App
from wall_auto_stability import slenderness_limit,panel_parameters,moment_ratio
from wall_crack_diagnostic import diagnose

class AutoStabilityTests(unittest.TestCase):
    def designer(self):
        return WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',axial_convention='Tracção positiva',wk_check_enabled=True)
    def data(self):
        return clean_dataframe(pd.DataFrame([dict(panel=1,node=i,case=c,nxx=-300,nyy=-400,nxy=1,mxx=mx,myy=my,mxy=1,qxx=1,qyy=1) for c,mx,my in [(101,10,20),(302,4,10)] for i in range(1,5)]))
    def nodes(self):
        return {'1':(0,0,0,''),'2':(4,0,0,''),'3':(0,0,3,''),'4':(4,0,3,'')}
    def test_limit(self):
        expected=20/(1+.2*1.5)*math.sqrt(1+2*2000*435/(250000*20))*.7/math.sqrt(400/(250*20))
        self.assertAlmostEqual(slenderness_limit(400,250,20,2000,435,1.5),expected)
    def test_geometry_creep(self):
        d=self.designer(); p=panel_parameters(self.data(),self.nodes(),d,1,.8,70,28,2,ec2_final_creep)
        self.assertAlmostEqual(p['l0_x'],4000); self.assertAlmostEqual(p['l0_y'],2400)
        self.assertEqual(p['h0'],250); self.assertAlmostEqual(p['phi_x'],p['phi_final']*.4);self.assertAlmostEqual(p['phi_y'],p['phi_final']*.5)
    def test_qp_missing(self):
        d=self.designer(); df=self.data(); self.assertIsNone(moment_ratio(df[df.case==101],d,'X'))
    def test_duplicate_rejected(self):
        d=self.designer(); df=self.data(); self.assertIsNone(moment_ratio(pd.concat([df,df.iloc[-1:]]),d,'X'))
    def test_full_automation(self):
        d=self.designer(); d.auto_stability=(self.nodes(),(1,.8,70,28,2));d.shell_qp_diagnostic=True
        r=d.design_dataframe(self.data()); self.assertAlmostEqual(r.iloc[0].Stability_X_l0_mm,4000);self.assertAlmostEqual(r.iloc[0].Stability_Y_l0_mm,2400)
        self.assertIn(r.iloc[0].Stability_X_status,['Dispensada (λ < λlim)','Incluída (rigidez nominal)','Instável no modelo de faixa'])
        self.assertTrue(r[r.Combo_type=='ELS-QP'].wk_max_mm.isna().all());self.assertTrue(r[r.Combo_type=='ELS-QP'].ShellQP_status.notna().all())
    def test_tension_does_not_require_length(self):
        d=self.designer();df=self.data();df['nxx']=300;df['nyy']=400
        r=d.design_dataframe(df);self.assertEqual(r.iloc[0].Stability_X_status,'Não requerida (N ≤ 0)');self.assertNotIn('definir l0',r.iloc[0].Verification_reason)
    def test_slenderness_dispenses(self):
        d=self.designer();d.effective_length_mm=1000;d.creep_effective=1
        r=d.design_dataframe(self.data());self.assertEqual(r.iloc[0].Stability_X_status,'Dispensada (λ < λlim)')
    def test_shell_diagnostic_symmetric_tension(self):
        r=diagnose(250,(100,200,0),(0,0,0),[500]*4,50,30000)
        self.assertAlmostEqual(r['ShellQP_sigma_x_plus_MPa'],100,places=4);self.assertAlmostEqual(r['ShellQP_sigma_y_plus_MPa'],200,places=4)
        self.assertNotIn('wk_mm',r)

    def test_unconfirmed_direction(self):
        d=self.designer();d.auto_stability=(self.nodes(),(0,1,70,28,2));r=d.design_dataframe(self.data())
        self.assertEqual(r.iloc[0].Stability_X_status,'Pendente: l0')
        self.assertEqual(r.iloc[0].Stability_X_l0_mm,0)
        self.assertAlmostEqual(r.iloc[0].Stability_Y_l0_mm,3000)

    def test_experimental_indicator_no_verdict(self):
        r=diagnose(250,(100,200,0),(0,0,0),[500]*4,50,30000,[(12,200)]*4)
        self.assertGreater(r['ShellQP_indicator_max_mm'],0)
        self.assertIn('wk pendente',r['ShellQP_status'])
        self.assertNotIn('wk_mm',r)
