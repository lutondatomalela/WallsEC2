import unittest
import numpy as np
import pandas as pd
from wall_physical_layers import layout
from wall_resultant_shear import resultant_shear,transfer_shear_reserve,check_additional_shear
from wall_sandwich_design import exact_aligned_faces,layers,elastic_face,compression_limit,face_opt
import test_service_loads

class ClosureChecks(unittest.TestCase):
    def test_reserve_lower_bound_all_directions(self):
        fam=layout(250,30,[[(1,12,200)],[(1,10,200)],[(1,16,200)],[(1,12,200)]])
        n=np.array([[-130,100,30],[90,-250,40],[0,0,0.]])
        q=np.array([[20,15],[10,-20],[5,0.]])
        cap,res=transfer_shear_reserve(250,fam,n,q,30,20,1.5)
        self.assertTrue(np.all(cap>0));np.testing.assert_allclose(res,cap-np.linalg.norm(q,axis=1))
        for a in np.linspace(0,2*np.pi,361):
            direction=np.tile([np.cos(a),np.sin(a)],(len(n),1))
            ref=resultant_shear(250,fam,n,direction,30,20,1.5,compression_credit=False)['PhysShear_VRdc_kN_m']
            self.assertTrue(np.all(cap<=ref+1e-10))
    def test_bound_is_not_assumed_and_exceedance_not_nc(self):
        state=check_additional_shear([100,100,100,100],[20]*4,[np.nan,-1,80,81])
        self.assertEqual(state.tolist(),['Dados insuficientes','Dados insuficientes','Limite sem armadura específica satisfeito','Limite sem armadura específica não demonstrado'])
    def test_exact_aligned_equilibrium_and_bounds(self):
        fam=layout(250,30,[[(1,12,200)]]*4);ls=layers(250,fam,(75,80));n=np.array([[20,50,80],[0,0,100],[-50,-30,5.]])
        m=np.array([[1.,-1.,.5],[0,0,0],[0,0,0.]])
        ep,em=[elastic_face(250,n,m,L[1]) for L in ls]
        p,sp,sm,score=exact_aligned_faces(n,m*1000,ls,(ep,em),30,20,500/1.15)
        good=np.isfinite(score);self.assertGreaterEqual(good.sum(),2)
        b=n-p;moment=ls[0][1]*p+ls[1][1]*b;moment[:,:2]+=(ls[0][3]-ls[0][1])*sp+(ls[1][3]-ls[1][1])*sm
        np.testing.assert_allclose(moment[good],m[good]*1000,atol=1e-9)
        for f,s,L,e in ((p,sp,ls[0],ep),(b,sm,ls[1],em)):
            _,u,ok,_,_,rule,sr=compression_limit(f[good],s[good],L[0],30,20,500/1.15,L[2],e[good]);self.assertTrue(ok.all());self.assertFalse(np.char.startswith(rule.astype(str),'Limite').any())
            opt=face_opt(f[good]);self.assertTrue(np.all(s[good]>=.5*opt-1e-7));self.assertTrue(np.all(s[good]<=2*opt+1e-7))
    def test_service_72_by_combination(self):
        d=test_service_loads.ServiceLoadTests();r=d.run_case();car=r[r.Combo_type.eq('ELS-CAR')].iloc[0];qp=r[r.Combo_type.eq('ELS-QP')].iloc[0];freq=r[r.Combo_type.eq('ELS-FREQ')].iloc[0]
        self.assertEqual(car.ELS_72_lim_c_MPa,18);self.assertEqual(car.ELS_72_lim_s_MPa,400);self.assertEqual(qp.ELS_72_lim_c_MPa,13.5);self.assertTrue(np.isnan(qp.ELS_72_lim_s_MPa));self.assertEqual(car.ELS_72_estado,'Limites satisfeitos (condicional)');self.assertEqual(freq.ELS_72_estado,'Sem limite específico 7.2 em FREQ')
        for r in (d.run_case(large=True),d.run_case(omit=True)):
            self.assertFalse(r.ELS_72_estado.eq('Limites satisfeitos (condicional)').any())

    def test_interlayer_bound_binding_and_nonpromotion(self):
        import copy,tempfile
        from pathlib import Path
        from wall_external_stability import calculation_scope
        from wall_interlayer_check import template,evaluate,CHECKS
        r=pd.DataFrame(dict(Panel=['A','A'],Node=['1','2'],Case=['101','101'],Combo_type=['ELU']*2,Case_coverage=['Completo']*2,Sand_transfer_reserve_kN_m=[70.,60.],Sand_transfer_VRdc_lower_kN_m=[90.,90.],Sand_Asw_req_mm2_m2=[0.,0.],Sand_util=[.1,.2],Sand_strip_order_status=['Dispensada']*2,Sand_transfer_status=['LL.115']*2))
        sc=calculation_scope(version='candidate',settings={},efforts=r,nodes={},results=r)
        t=template(sc,r);t.update(responsavel='Teste',referencia_relatorio='REF',metodo='Exemplo sintético',confirmacoes={k:True for k in CHECKS})
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'report.txt';report.write_text('Exemplo sintético')
            for v,state in [(None,'Condicionado — dados insuficientes'),(60.,'Satisfeito com limite externo'),(61.,'Condicionado — reserva insuficiente')]:
                t['paineis'][0]['limite_corte_adicional_kN_m']=v
                self.assertEqual(evaluate(sc,r,t,report).iloc[0].Estado_intercamadas,state)
            t['paineis'][0]['limite_corte_adicional_kN_m']=False
            with self.assertRaises(ValueError):evaluate(sc,r,t,report)
            t['paineis'][0]['limite_corte_adicional_kN_m']=0.
            t['scope_sha256']='bad'
            with self.assertRaises(ValueError):evaluate(sc,r,t,report)

    def test_uniaxial_service_uses_cracked_and_intact(self):
        from WallsEC2 import WallDesigner,clean_dataframe
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',axial_convention='Tracção positiva',wk_check_enabled=True)
        d.sandwich_design=True
        rows=[dict(panel=1,node=1,case=c,nxx=0,nyy=0,nxy=0,mxx=5,myy=0,mxy=0,qxx=0,qyy=0) for c in (101,302,303,311)]
        r=d.design_dataframe(clean_dataframe(pd.DataFrame(rows)));car=r[r.Combo_type.eq('ELS-CAR')].iloc[0]
        self.assertEqual(car.ELS_72_estado,'Limites satisfeitos (faixa N-M)');self.assertIn('fendilhada',car.ELS_72_modelo)
        self.assertGreaterEqual(car.ELS_72_eta_s,car.ELS_X_sigma_s_cracked_MPa/400)
        self.assertGreaterEqual(car.ELS_72_eta_c,car.ELS_X_sigma_c_cracked_MPa/18)

    def test_gui_interlayer_import_stays_separate(self):
        from WallsEC2 import WallsEC2App,WallDesigner,clean_dataframe
        from wall_interlayer_check import template,CHECKS
        from unittest.mock import patch
        import tkinter as tk,json,tempfile
        from pathlib import Path
        try:a=WallsEC2App()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.addCleanup(a.destroy);a.withdraw()
        a.df_clean=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=101,nxx=5,nyy=5,nxy=2,mxx=1,myy=.5,mxy=.2,qxx=1,qyy=1)]))
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',axial_convention='Tracção positiva');d.sandwich_design=True
        a.df_results=d.design_dataframe(a.df_clean);a.df_summary=a.build_panel_summary(a.df_results);before=a.df_summary.Status_global.copy();a._calculated_signature=a._input_signature()
        t=template(a._external_scope(),a.df_results);t.update(responsavel='Teste',referencia_relatorio='Exemplo',metodo='Exemplo sintético',confirmacoes={k:True for k in CHECKS})
        t['paineis'][0]['limite_corte_adicional_kN_m']=10.
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'r.txt';report.write_text('Caso sintético');decl=Path(folder)/'d.json';decl.write_text(json.dumps(t))
            with patch('WallsEC2.filedialog.askopenfilename',side_effect=[str(decl),str(report)]),patch('WallsEC2.messagebox.askyesno',return_value=True),patch('WallsEC2.messagebox.showerror',side_effect=AssertionError):a.interlayer_import()
        self.assertEqual(a.df_interlayer.iloc[0].Estado_intercamadas,'Satisfeito com limite externo');self.assertIn('Satisfeito',a.df_summary.Transferencia_faces.iloc[0]);pd.testing.assert_series_equal(before,a.df_summary.Status_global)
