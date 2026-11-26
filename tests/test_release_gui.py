import unittest
import tkinter as tk
from unittest.mock import patch
import pandas as pd
from WallsEC2 import WallsEC2App, WallDesigner, clean_dataframe

class ReleaseGuiTests(unittest.TestCase):
    def setUp(self):
        try: self.app = WallsEC2App()
        except tk.TclError as exc: self.skipTest(str(exc))
        self.addCleanup(self.app.destroy)
        self.app.withdraw()

    def test_quick_notes_and_instruction_include_tensor(self):
        def descend(widget):
            yield widget
            for child in widget.winfo_children(): yield from descend(child)
        labels=[]; texts=[]
        for widget in descend(self.app):
            try: labels.append(str(widget.cget('text')))
            except tk.TclError: pass
            if isinstance(widget, tk.Text): texts.append(widget.get('1.0','end'))
        notes=next(t for t in labels if 'Nxx, Nyy, Nxy — membrana' in t)
        self.assertIn('Mxx, Myy, Mxy',notes)
        self.assertIn('Qxx, Qyy',notes)
        self.assertTrue(any('NXX | NYY | NXY | MXX | MYY | MXY | QXX | QYY' in t for t in texts))

    def test_main_views_hide_internal_fields_and_preserve_values(self):
        df=pd.DataFrame([dict(Panel=1,Status_global='OK*',util_max=.42,Sand_util_max=.6,Estabilidade_global_externa='Não avaliada',casca_experimental_max=.5)])
        self.app.df_summary=df.copy();self.app.df_results=pd.DataFrame([{'Sand_status':'Satisfeito'}])
        self.app.show_df(self.app.tree_summary,df)
        self.assertNotIn('Estabilidade_global_externa',self.app.tree_summary['columns'])
        self.assertNotIn('casca_experimental_max',self.app.tree_summary['columns'])
        self.assertEqual(self.app.tree_summary.heading('util_max','text'),'η faixa')
        self.assertEqual(self.app.tree_summary.item(self.app.tree_summary.get_children()[0],'values')[1],'Cumpre sob hipóteses')
        pd.testing.assert_frame_equal(df,self.app.df_summary)
        self.app.refresh_dashboard()
        self.assertNotIn('Estabilidade global externa',self.app.dashboard_tree['columns'])
        self.assertIn('η sandwich',self.app.dashboard_tree['columns'])

    def test_input_audit_reports_missing_membrane_row(self):
        d=WallDesigner(250,30,'C30/37',500)
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=101,mxx=1,myy=2,mxy=0,nxx=0,nyy=0,nxy=1,qxx=0,qyy=0),dict(panel=1,node=2,case=101,mxx=1,myy=2,mxy=0,nxx=0,nyy=0,nxy=0,qxx=0,qyy=0)]))
        df.loc[df.index[1], "__missing_nxy"] = True
        checks=self.app.build_data_validation(df,d)
        row=checks[checks.Item.eq('NXY')].iloc[0]
        self.assertEqual(row.Estado,'Verificar')
        self.assertIn('1/2',row.Resultado)
