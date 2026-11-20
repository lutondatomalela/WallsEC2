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
                rows.append(dict(panel=panel,node=1,case=case,mxx=3,myy=3,mxy=0,qxx=0,qyy=0,
                                 nxx=-100,nyy=-100,nxy=10 if panel==2 else 0))
        df=clean_dataframe(pd.DataFrame(rows))
        d=WallDesigner(200,30,'C30/37',500,elu_cases='101',qp_case='203',wk_check_enabled=True,
                       axial_convention='Compressão positiva')
        app.df_results=d.design_dataframe(df)
        app.df_summary=WallsEC2App.build_panel_summary(app,app.df_results)
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
            self.assertIn(b'Majora',content)

if __name__=='__main__': unittest.main()
