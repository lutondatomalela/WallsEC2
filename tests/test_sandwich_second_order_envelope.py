import unittest
import numpy as np
import pandas as pd
from WallsEC2 import WallDesigner, WallsEC2App, clean_dataframe
from wall_sandwich_design import assess_envelope, _run

class SandwichSecondOrderTests(unittest.TestCase):
    def setUp(self):
        self.d=WallDesigner(250,30,'C30/37',500,elu_cases='101',axial_convention='Tracção positiva',effective_length_mm=3000,creep_effective=1.5)
        self.mesh=['Ø12//200']*4
    def test_envelope_matches_independent_cases_and_signed_input(self):
        n=np.array([[-70.,-90.,20.]]);m=np.array([[8.,-12.,3.]]);q=np.array([[10.,-20.]])
        delta=np.array([[2.,4.]])
        r=assess_envelope(self.d,self.mesh,n,m,q,delta)
        trials=[]
        for i in (-1,0,1):
            for j in (-1,0,1):
                mt=m+np.array([[i*2,j*4,0.]])
                trial=_run(self.d,self.mesh,n,mt,q)
                trials.append((trial['util'][0],mt,trial))
        worst=max(trials,key=lambda t:t[0]);self.assertEqual(r['envelope_count'][0],9)
        self.assertAlmostEqual(r['util'][0],worst[0]);self.assertGreaterEqual(r['util'][0],r['util_first_order'][0])
        np.testing.assert_allclose([r['MEd_x_kNm_m'][0],r['MEd_y_kNm_m'][0]],worst[1][0,:2]);self.assertLess(r['residual_kNm_m'][0],1e-7)
        for f in ('X+','X-','Y+','Y-'):self.assertAlmostEqual(r['As_req_'+f][0],max(t[2]['As_req_'+f][0] for t in trials))
    def test_zero_missing_and_partial_allowance(self):
        n=np.array([[-70.,-90.,20.]]);m=np.array([[8.,-12.,3.]]);q=np.array([[10.,-20.]])
        r=assess_envelope(self.d,self.mesh,n,m,q,[[0,0]])
        self.assertEqual(r['envelope_count'][0],1);self.assertEqual(r['util'][0],r['util_first_order'][0]);self.assertTrue(r['allowance_complete'][0])
        r=assess_envelope(self.d,self.mesh,n,m,q,[[np.nan,2]])
        self.assertFalse(r['allowance_complete'][0]);self.assertEqual(r['envelope_count'][0],3);self.assertTrue(np.isnan(r['delta_Mx_kNm_m'][0]))
    def test_oblique_not_a_separate_second_order_pending(self):
        self.d.sandwich_design=True
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=j,case=101,nxx=-40,nyy=-30,nxy=xy,mxx=2,myy=3,mxy=1,qxx=2,qyy=2) for j,xy in [(1,0),(2,10)]]))
        r=self.d.design_dataframe(df)
        self.assertNotIn('Sand_second_order_status',r)
        self.assertTrue(r.Sand_strip_order_status.str.startswith('Dispensada').all())
        s=WallsEC2App.build_panel_summary(None,r).iloc[0]
        self.assertNotIn('Segunda_ordem_casca',s.index)
        self.assertEqual(s.Sand_2ordem_pendente,0)
        self.assertNotIn('segunda ordem acoplada',s.Motivo_estado)
        self.assertEqual(s.Status_global,'OK*')
        self.assertNotIn('sandwich: amarração',s.Motivo_estado)
    def test_missing_strip_parameters_remain_pending(self):
        self.d.sandwich_design=True;self.d.effective_length_mm=0
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=101,nxx=-40,nyy=-30,nxy=10,mxx=2,myy=3,mxy=1,qxx=2,qyy=2)]))
        r=self.d.design_dataframe(df)
        self.assertEqual(r.iloc[0].Sand_strip_order_status,'Dados locais pendentes')
        s=WallsEC2App.build_panel_summary(None,r).iloc[0]
        self.assertEqual(s.Sand_2ordem_pendente,1)
        self.assertIn('incrementos de segunda ordem por faixa pendentes',s.Motivo_estado)
    def test_nominal_stiffness_amplification_entered_in_sandwich(self):
        d=self.d;d.effective_length_mm=6000.;d.sandwich_design=True
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=101,nxx=-250,nyy=0,nxy=0,mxx=12,myy=0,mxy=0,qxx=0,qyy=0)]))
        r=d.design_dataframe(df).iloc[0]
        self.assertIn('Incluída',r.Stability_X_status)
        self.assertGreater(r.Stability_X_amplification,1)
        self.assertAlmostEqual(r.Sand_delta_Mx_kNm_m,abs(r.NM_X_MEd)-max(r['Mx+_WA'],r['Mx-_WA']))
        self.assertGreater(r.Sand_util,r.Sand_util_first_order)
        self.assertEqual(r.Sand_envelope_count,3)
