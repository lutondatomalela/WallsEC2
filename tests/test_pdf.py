import inspect
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from WallsEC2 import WallsEC2App,WallDesigner,clean_dataframe
from test_export import Variable

class PdfRegressionTests(unittest.TestCase):
    def test_export_keeps_unassessed_panel_and_nm_table(self):
        app=SimpleNamespace(update_idletasks=lambda:None,progress_var=Variable(),status_var=Variable())
        source=inspect.getsource(WallsEC2App.export_pdf_report)
        for name in set(re.findall(r'self\.(var_\w+)',source)):
            setattr(app,name,Variable('0'))
        for name in set(re.findall(r'self\.(df_\w+)',source)):
            setattr(app,name,pd.DataFrame())
        for name,value in dict(var_qp_case='203',var_elu_cases='101',var_axial_convention='Compressão positiva',
             var_thickness='200',var_cover='30',var_concrete='C30/37',var_steel='500',var_wmax='.3',
             var_crack_check=True,var_y_vertical=True,var_optimize_rebar=False,var_swap_axes=False).items():
            setattr(app,name,Variable(value))
        rows=[]
        for panel in [1,2]:
            for case in [101,203]:
                rows.append(dict(panel=panel,node=1,case=case,mxx=3,myy=3,mxy=0,qxx=20 if case==101 else 0,qyy=0,
                                 nxx=-100,nyy=-100,nxy=10 if panel==2 else 0))
        df=clean_dataframe(pd.DataFrame(rows))
        d=WallDesigner(200,30,'C30/37',500,elu_cases='101',qp_case='203',wk_check_enabled=True,
                       axial_convention='Compressão positiva')
        d.shell_qp_diagnostic=True
        from wall_core_equilibrium import CoreTrial
        with patch('wall_core_equilibrium.CoreEquilibrium.assess',return_value=CoreTrial('Sem solução; ensaio',face_util=1.1)):
            app.df_results=d.design_dataframe(df)
        self.assertIn('Asym_status',app.df_results)
        self.assertIn('AsymTruss_status',app.df_results)
        app.df_summary=WallsEC2App.build_panel_summary(app,app.df_results)
        app.df_external_stability=pd.DataFrame([dict(Panel="1",Estabilidade_global_externa="Não conforme (declaração externa)",responsavel="Teste",metodo="Modelo externo",referencia_relatorio="SYNTH-1")])
        with tempfile.TemporaryDirectory() as folder:
            target=str(Path(folder)/'report.pdf')
            with patch('WallsEC2.filedialog.asksaveasfilename',return_value=target), \
                 patch('reportlab.rl_config.pageCompression',0), \
                 patch('WallsEC2.messagebox.showerror',side_effect=AssertionError):
                WallsEC2App.export_pdf_report(app)
            content=Path(target).read_bytes()
            self.assertTrue(content.startswith(b'%PDF-'))
            self.assertIn(b'N-M',content)
            self.assertIn(b'avaliado',content)
            self.assertIn(b'Envolvente ELU',content)
            self.assertIn(b'equil',content)
            self.assertIn(b'bandas assim',content)
            self.assertIn(b'alternativa com treli',content)
            self.assertIn(b'SYNTH-1',content)

    def test_adopted_rebar_governing_case_excludes_service(self):
        d = WallDesigner(200, 30, "C30/37", 500, elu_cases="101", qp_case="203",
                         axial_convention="Compressão positiva")
        rows = [dict(panel=1, node=case, case=case, mxx=10, myy=10, mxy=0,
                     qxx=0, qyy=0, nxx=100, nyy=100, nxy=0) for case in (101, 203)]
        results = d.design_dataframe(clean_dataframe(pd.DataFrame(rows)))
        results.loc[results["Combo_type"] == "ELS-QP", "util_max"] = 99.
        row = WallsEC2App.build_governing_design(None, results).iloc[0]
        self.assertEqual(row["governing_role"], "ELU")
        self.assertEqual(row["governing_case"], 101)
        self.assertLess(row["util_max"], 99.)
        panel = WallsEC2App.build_panel_summary(None, results).iloc[0]
        self.assertEqual(panel["caso_governante"], 101)
        self.assertEqual(panel["Status_global"], "Incompleto")
        self.assertNotIn("Corte", panel["Motivo_estado"])
        failed = results.copy()
        failed.loc[failed["Combo_type"].eq("ELU"), "util_Qy"] = 1.01
        verdict, why = WallsEC2App.panel_outcome(failed)
        self.assertEqual(verdict, "Não conforme")
        self.assertIn("Corte Y", why)
        nm = WallsEC2App.build_nm_envelope(results)
        self.assertEqual(set(nm["Direcção"]), {"X", "Y"})
        self.assertEqual(set(nm["Case"]), {101})
        self.assertTrue(nm["Segunda ordem"].eq("Pendente: l0").all())

    def test_shear_trace_uses_same_face_area_and_depth(self):
        from WallsEC2 import RebarSolution
        d = WallDesigner(250, 30, "C30/37", 500, axial_convention="Compressão positiva",
                         elu_cases="101", phi_max_mm=20)
        row = clean_dataframe(pd.DataFrame([dict(panel=1, node=1, case=101,
            mxx=10, myy=10, mxy=0, qxx=20, qyy=80, nxx=0, nyy=200, nxy=0)])).iloc[0]
        x = RebarSolution(20, 200, 1570.)
        y1, y2 = RebarSolution(10, 100, 785.), RebarSolution(12, 200, 565.)
        result = d.design_one(row, adopted=[x, x, y1, y2])
        self.assertEqual(result["Shear_Y_face_VRdc"], "-")
        self.assertEqual(result["Shear_Y_As_mm2_m"], 565.)
        self.assertEqual(result["Shear_Y_d_mm"], 214.)
        self.assertAlmostEqual(result["VRdc_y_kN_m"], d.shear_vrdc_kN_per_m(565., 214., .8))

if __name__=='__main__': unittest.main()
