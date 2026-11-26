import unittest
import numpy as np
import pandas as pd
from wall_physical_layers import PhysicalCapacity,layout
from wall_adaptive_capacity import solve
from wall_case_audit import case_audit
from WallsEC2 import canonical_case_id, WallDesigner,clean_dataframe

class AdaptiveCapacityTests(unittest.TestCase):
    def setUp(self):
        self.f=layout(250,30,[[(1,12,200)]]*4)
        self.model=PhysicalCapacity(250,self.f,435,10,subdivisions=3,directions=8)
    def test_pure_tension_exact(self):
        a=solve(self.model,[200,0,0],[0,0,0]);self.assertTrue(a.converged)
        self.assertAlmostEqual(a.util,self.model.check([200,0,0],[0,0,0])[0],places=9)
    def test_dense_orientation_bound(self):
        dense=PhysicalCapacity(250,self.f,435,10,subdivisions=3,directions=256)
        for n,m in [([-200,-100,55],[5,-10,9]),([-900,-600,300],[8,10,5]),([100,100,100],[0,0,0])]:
            a=solve(self.model,n,m); fac=1/dense.check(n,m)[0]
            self.assertLessEqual(a.residual,1e-6)
            self.assertGreaterEqual(a.factor_upper+1e-6,fac)
            self.assertGreaterEqual(a.factor_lower+1e-7,1/self.model.check(n,m)[0])
            self.assertLessEqual(abs(a.factor_lower-fac)/fac,5e-4)
    def test_zero_and_reflection(self):
        self.assertEqual(solve(self.model,[0]*3,[0]*3).util,0)
        a=solve(self.model,[-200,-100,55],[5,-10,9]);b=solve(self.model,[-200,-100,-55],[5,-10,-9]);self.assertAlmostEqual(a.util,b.util,places=6)
    def test_invalid(self):
        with self.assertRaises(ValueError):solve(self.model,[1,2,np.nan],[0,0,0])
    def test_omitted_node_detected(self):
        df=pd.DataFrame([dict(panel=1,node=2,case=101),dict(panel=1,node=3,case=102)])
        a=case_audit(df,{'101'},canonical_case_id);self.assertEqual(a.Casos_presentes.tolist(),[1,0])
        self.assertEqual(a.Estado.tolist(),['Completo','Incompleto'])
    def test_design_refuses_silent_drop(self):
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',axial_convention='Tracção positiva')
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=n,case=c,mxx=10,myy=1,mxy=0,nxx=0,nyy=0,nxy=0,qxx=0,qyy=0) for n,c in [(2,101),(3,102)]]))
        with self.assertRaisesRegex(ValueError,'sem qualquer combinação'):d.design_dataframe(df)

    def test_modal_tensor_cannot_be_silently_approved(self):
        from WallsEC2 import WallsEC2App
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',axial_convention='Tracção positiva')
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case='101 (CQC)',mxx=10,myy=1,mxy=0,nxx=0,nyy=0,nxy=0,qxx=0,qyy=0)]))
        r=d.design_dataframe(df)
        state, reason= WallsEC2App.panel_outcome(r)
        self.assertIn('concomitância por confirmar',reason)
        self.assertEqual(state,'Incompleto')
