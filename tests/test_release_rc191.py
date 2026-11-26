import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from wall_physical_layers import PhysicalCapacity,layout,crack_candidate,summary
from WallsEC2 import WallsEC2App

class DistributedBands(unittest.TestCase):
    def setUp(self):
        self.f=layout(250,30,[[(1,12,200)]]*4)
    def test_subdivided_capacity_budget_and_centers(self):
        a=PhysicalCapacity(250,self.f,435,10)
        b=PhysicalCapacity(250,self.f,435,10,subdivisions=3)
        self.assertEqual(len(b.cap),6)
        self.assertAlmostEqual(sum(a.cap),sum(b.cap))
        np.testing.assert_allclose(b.centers,-np.array(b.centers[3:]+b.centers[:3]))
        self.assertAlmostEqual(b.check([-1000,0,0],[0,0,0])[0],1000/sum(b.cap),places=7)
    def test_outer_subband_equilibrium(self):
        b=PhysicalCapacity(250,self.f,435,10,subdivisions=3)
        # Independently constructed compression force and its moment at first strip.
        force=0.9*b.cap[0]; mom=-force*b.centers[0]/1000
        u,res,_=b.check([-force,0,0],[mom,0,0])
        self.assertLessEqual(u,0.9000001);self.assertLess(res,1e-6)
        self.assertIsNotNone(b.required_areas([-force,0,0],[mom,0,0]))
    def test_reflection(self):
        b=PhysicalCapacity(250,self.f,435,10,subdivisions=3)
        u=b.check([-200,-100,55],[5,-10,9])[0]
        v=b.check([-200,-100,-55],[5,-10,-9])[0]
        self.assertAlmostEqual(u,v,places=8)
    def test_candidate_compression_not_wk(self):
        q=crack_candidate(250,self.f,[-100,-100,0],[0,0,0],30000,2.9)
        self.assertEqual(q['PhysQP_candidate_max_mm'],0)
        self.assertTrue(q['PhysQP_complete_candidate'])
        self.assertIn('história desconhecida',q['PhysQP_reason_plus'])
        self.assertNotIn('wk_max_mm',q)
    def test_coverage_does_not_hide_failure(self):
        r=pd.DataFrame({'Panel':[1]*5,'Node':range(5),'Case':[101,101,101,302,302],'Combo_type':['ELU']*3+['ELS-QP']*2,'PhysELU_util':[.5,1.2,np.nan,np.nan,np.nan],'PhysQP_complete_candidate':[False,False,False,True,False]})
        a,b=summary(r).to_dict('records')
        self.assertEqual(a['PhysELU_insuficientes'],1);self.assertEqual(a['PhysELU_sem_resultado'],1)
        self.assertEqual(b['PhysQP_completas'],1);self.assertEqual(b['PhysQP_parciais'],1)

class Toolbar(unittest.TestCase):
    def test_unique_actions_and_stale_export(self):
        import tkinter as tk
        try: app=WallsEC2App()
        except tk.TclError as exc: self.skipTest(str(exc))
        self.addCleanup(app.destroy);app.withdraw()
        def walk(w):
            for child in w.winfo_children():
                yield child;yield from walk(child)
        labels=[w.cget('text') for w in walk(app) if w.winfo_class()=='TButton']
        for label in ('Importar esforços','Importar nós','Calcular'):
            self.assertEqual(labels.count(label),1)
        self.assertEqual(labels.count('Relatório PDF'),0)
        app.df_results=pd.DataFrame({'x':[1]});app._calculated_signature=app._input_signature()
        self.assertTrue(app._export_current());app.var_thickness.set('300')
        with patch('WallsEC2.messagebox.showwarning') as msg,patch('WallsEC2.filedialog.asksaveasfilename') as dialog:
            app.export_pdf_report();msg.assert_called_once();dialog.assert_not_called()
