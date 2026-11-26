"""Synthetic geometry tests independent of all private project records."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import pandas as pd
from WallsEC2 import WallsEC2App, WallDesigner,clean_dataframe
from wall_geometry import read_nodes,geometry_tables
from tools.calcular_paineis import calculate_parallel

class PublicGeometry(TestCase):
    def fixture(self,tmp):
        p=Path(tmp)/'nodes.csv'
        points=[(0,0,0),(2,0,0),(0,0,3),(2,0,3),(4,0,0),(4,0,3)]
        p.write_text('Node;X(m);Y(m);Z(m)\n'+'\n'.join(f'{i};{x};{y};{z}' for i,(x,y,z) in enumerate(points,1)),encoding='utf-8')
        df=clean_dataframe(pd.DataFrame([dict(panel=panel,node=node,case=case,nxx=-10,nyy=-40,nxy=2,mxx=2,myy=3,mxy=.5,qxx=1,qyy=1) for panel,nodes in [('A',[1,2,3,4]),('B',[2,4,5,6])] for node in nodes for case in [101,302]]))
        return p,df
    def test_synthetic_geometry(self):
        with TemporaryDirectory() as tmp:
            p,df=self.fixture(tmp); summary,details=geometry_tables(df,read_nodes(p))
            self.assertEqual(len(summary),2);self.assertEqual(len(details),8);self.assertEqual(summary.nos_em_falta.sum(),0)
            self.assertTrue(summary.estado.eq('Plano identificado').all());self.assertFalse(summary.altura_livre_confirmada.any())
    def test_synthetic_parallel(self):
        with TemporaryDirectory() as tmp:
            p,df=self.fixture(tmp)
            settings=dict(thickness_mm=250,cover_mm=30,concrete_class='C30/37',fyk=500,elu_cases='101',qp_case='302',axial_convention='Tracção positiva',wk_check_enabled=True)
            opts=(1.,1.,70.,28.,2);d=WallDesigner(**settings);d.sandwich_design=True;d.auto_stability=(read_nodes(p),opts)
            serial=d.design_dataframe(df);parallel=calculate_parallel(df,settings,str(p),opts,2)
            pd.testing.assert_frame_equal(serial,parallel,check_exact=False,rtol=1e-9,atol=1e-9)
    def test_window_icon(self):
        import tkinter as tk
        try:app=WallsEC2App()
        except tk.TclError as e:self.skipTest(str(e))
        self.addCleanup(app.destroy);app.withdraw();self.assertTrue(app.icon_loaded)
