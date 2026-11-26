import copy,json,tempfile,unittest
from pathlib import Path
import pandas as pd
from wall_external_stability import calculation_scope,template,validate_declaration,file_sha256,CHECKS

class ExternalStability(unittest.TestCase):
    def setUp(self):
        self.efforts=pd.DataFrame({'panel':[1,1,2], 'node':[10,10,20], 'case':[101,102,101], 'nxx':[20.,30.,40.]})
        self.results=pd.DataFrame({'Panel':[1,1,2], 'Node':[10,10,20], 'Case':[101,102,101], 'Combo_type':['ELU']*3,'Case_coverage':['Completo']*3,'X+_rebar':['12//200']*3})
        self.kw=dict(version='dev',settings={'h':250},efforts=self.efforts,nodes={'10':(0,0,1,'')},results=self.results)
        self.scope=calculation_scope(**self.kw)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.report=Path(self.tmp.name)/'report.txt';self.report.write_text('Relatório sintético externo')
        self.record=template(self.scope)
        self.record.update(responsavel='Responsável de teste',metodo='Modelo externo de 2ª ordem',referencia_relatorio='SYNTH-01',confirmacoes={k:True for k in CHECKS})
        self.record['paineis'][0]['estado']='Conforme';self.record['paineis'][1]['estado']='Não conforme'
    def test_valid(self):
        r=validate_declaration(self.scope,self.record,self.report)
        self.assertEqual(list(r.Estabilidade_global_externa),['Conforme (declaração externa)','Não conforme (declaração externa)'])
        self.assertTrue(r.Relatorio_SHA256.eq(file_sha256(self.report)).all())
    def test_modified_snapshot(self):
        for key,value in [('settings',{'h':220}),('nodes',{'10':(0,0,2,'')}),('version','other'),('efforts',self.efforts.assign(nxx=99)),('results',self.results.assign(**{'X+_rebar':'20//200'}))]:
            args=dict(self.kw);args[key]=value
            with self.assertRaises(ValueError):validate_declaration(calculation_scope(**args),self.record,self.report)
    def test_missing_and_duplicate_panels(self):
        for panels in ([self.record['paineis'][0]], [self.record['paineis'][0]]*2):
            r=dict(self.record,paineis=panels)
            with self.assertRaises(ValueError):validate_declaration(self.scope,r,self.report)
    def test_missing_case(self):
        r=copy.deepcopy(self.record);r['paineis'][0]['casos_elu']=['101']
        with self.assertRaises(ValueError):validate_declaration(self.scope,r,self.report)
    def test_incomplete_coverage(self):
        args=dict(self.kw);args['results']=self.results.assign(Case_coverage='Incompleto');scope=calculation_scope(**args)
        r=copy.deepcopy(self.record);r['scope_sha256']=scope['sha256']
        with self.assertRaises(ValueError):validate_declaration(scope,r,self.report)
    def test_confirmation_and_report_hash(self):
        r=copy.deepcopy(self.record);r['confirmacoes'][CHECKS[0]]=False
        with self.assertRaises(ValueError):validate_declaration(self.scope,r,self.report)
        r=copy.deepcopy(self.record);r['relatorio_sha256']='0'*64
        with self.assertRaises(ValueError):validate_declaration(self.scope,r,self.report)
    def test_ui_record_does_not_promote_local_status(self):
        from WallsEC2 import WallsEC2App,WallDesigner,clean_dataframe
        from unittest.mock import patch
        import tkinter as tk
        try:app=WallsEC2App()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.addCleanup(app.destroy);app.withdraw()
        app.df_clean=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=101,mxx=10,myy=10,mxy=0,qxx=0,qyy=0,nxx=100,nyy=100,nxy=0)]))
        app.df_results=WallDesigner(200,30,'C30/37',500,elu_cases='101',axial_convention='Compressão positiva').design_dataframe(app.df_clean)
        app.df_summary=app.build_panel_summary(app.df_results);before=app.df_summary.Status_global.copy();app._calculated_signature=app._input_signature()
        scope=app._external_scope();t=template(scope);t.update(responsavel='Teste',metodo='Análise global externa',referencia_relatorio='Ref 1',confirmacoes={k:True for k in CHECKS})
        t['paineis'][0]['estado']='Não conforme';decl=Path(self.tmp.name)/'decl.json';decl.write_text(json.dumps(t))
        with patch('WallsEC2.filedialog.askopenfilename',side_effect=[str(decl),str(self.report)]),patch('WallsEC2.messagebox.askyesno',return_value=True),patch('WallsEC2.messagebox.showerror',side_effect=AssertionError):app.external_stability_import()
        pd.testing.assert_series_equal(before,app.df_summary.Status_global)
        self.assertIn('Não conforme',app.df_summary.Estabilidade_global_externa.iloc[0]);self.assertIn('não conformes externos',app.dashboard_text.get())
