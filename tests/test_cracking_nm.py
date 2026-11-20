import math
import unittest
import pandas as pd
from wall_section import Section
from WallsEC2 import WallDesigner,clean_dataframe

class CompositeCrackingTests(unittest.TestCase):
    def section(self): return Section(200,44,1000,1000)
    def test_pure_tension_hand(self):
        s=self.section()
        r=s.cracking(-200,0,12,150,12,150)
        v=r['plus']
        rho=1000/(1000*100)
        fct=.3*30**(2/3)
        alpha=200000/(22000*3.8**.3)
        sr=3.4*(44-6)+.8*.425*12/rho
        eps=max((100-.4*fct/rho*(1+alpha*rho))/200000,.6*100/200000)
        self.assertAlmostEqual(v['sigma_s'],100)
        self.assertAlmostEqual(v['wk'],sr*eps)
        self.assertAlmostEqual(v['k2'],1)
        self.assertEqual(v['hc_eff'],100)
        self.assertEqual(v,r['minus'])

    def test_compression_no_cracks(self):
        r=self.section().cracking(200,0,12,150,12,150)
        self.assertEqual(r['plus']['wk'],0)
        self.assertEqual(r['minus']['wk'],0)

    def test_pure_bending_k2(self):
        r=self.section().cracking(0,20,12,150,12,150)
        self.assertAlmostEqual(r['plus']['k2'],.5)
        self.assertGreater(r['plus']['wk'],0)
        self.assertEqual(r['minus']['wk'],0)
        self.assertLess(r['plus']['hc_eff'],200/3)

    def test_reversal(self):
        a=self.section().cracking(-100,20,12,150,12,150)
        b=self.section().cracking(-100,-20,12,150,12,150)
        self.assertAlmostEqual(a['plus']['wk'],b['minus']['wk'])

    def test_large_spacing(self):
        r=self.section().cracking(-200,0,12,500,12,500)
        self.assertEqual(r['plus']['sr_max'],1.3*200)

    def test_stress_not_clipped(self):
        r=self.section().cracking(-2000,0,12,150,12,150)
        self.assertAlmostEqual(r['plus']['sigma_s'],1000)

    def test_eccentric_tension(self):
        r=self.section().cracking(-300,3,12,150,12,150)
        self.assertGreater(r['plus']['wk'],r['minus']['wk'])
        self.assertGreater(r['plus']['k2'],.5)
        self.assertLess(r['plus']['k2'],1)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError): self.section().cracking(0,10,12,0,12,100)
        with self.assertRaises(ValueError): self.section().cracking(float('nan'),10,12,100,12,100)

    def dataset(self,nxy=0,mxy=0):
        return clean_dataframe(pd.DataFrame([
            dict(panel=1,node=1,case=101,mxx=10,myy=10,mxy=0,qxx=0,qyy=0,nxx=-100,nyy=-100,nxy=0),
            dict(panel=1,node=1,case=203,mxx=3,myy=3,mxy=mxy,qxx=0,qyy=0,nxx=-100,nyy=-100,nxy=nxy)]))

    def designer(self,**kw):
        args=dict(elu_cases='101',qp_case='203',wk_check_enabled=True,axial_convention='Compressão positiva')
        args.update(kw)
        return WallDesigner(200,30,'C30/37',500,**args)

    def test_common_mesh_composite(self):
        r=self.designer().design_dataframe(self.dataset())
        qp=r.loc[r.Case==203].iloc[0]
        self.assertEqual(qp['Crack_model'],'N-M fendilhado')
        self.assertTrue(math.isfinite(qp['wk_max_mm']))
        self.assertGreater(qp['wk_max_mm'],0)
        self.assertEqual(r.iloc[0]['X+_rebar'],r.iloc[1]['X+_rebar'])
        self.assertGreaterEqual(qp['Asx+_prov_mm2_m'],.3*30**(2/3)*1000*100/500)

    def test_coupled_actions_do_not_get_false_wk(self):
        for df in [self.dataset(nxy=10),self.dataset(mxy=3)]:
            qp=self.designer().design_dataframe(df).iloc[1]
            self.assertTrue(math.isnan(qp['wk_max_mm']))
            self.assertEqual(qp['Crack_control_status'],'Não avaliado')

    def test_unknown_sign_not_approved(self):
        qp=self.designer(axial_convention='Não definida').design_dataframe(self.dataset()).iloc[1]
        self.assertTrue(math.isnan(qp['wk_max_mm']))
        self.assertEqual(qp['Status'],'Verificar')

    def test_axial_only_is_not_empty_data(self):
        df=self.dataset()
        df['mxx']=0.;df['myy']=0.
        r=self.designer().design_dataframe(df)
        self.assertNotIn('Dados insuficientes',r.Status.tolist())

    def test_each_panel_needs_qp(self):
        df=self.dataset()
        missing=df.iloc[[0]].copy()
        missing['panel']='other'
        r=self.designer().design_dataframe(pd.concat([df,missing],ignore_index=True))
        other=r[r.Panel=='other'].iloc[0]
        self.assertEqual(other.Status,'Verificar')
        self.assertIn('Painel sem combinação QP',other['Verification_reason'])

    def test_input_sign_equivalence(self):
        df=self.dataset()
        a=self.designer().design_dataframe(df).iloc[1]
        df['nxx']*=-1;df['nyy']*=-1
        b=self.designer(axial_convention='Tracção positiva').design_dataframe(df).iloc[1]
        self.assertAlmostEqual(a['wk_max_mm'],b['wk_max_mm'])

if __name__=='__main__': unittest.main()
