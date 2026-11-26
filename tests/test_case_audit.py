import unittest
import pandas as pd
from wall_case_audit import case_audit
from WallsEC2 import canonical_case_id, WallDesigner, clean_dataframe, WallsEC2App

class CaseAuditTests(unittest.TestCase):
    def test_missing_at_node_not_hidden_by_other_node(self):
        df=pd.DataFrame([dict(panel=1,node=2,case=101),dict(panel=1,node=3,case=102)])
        a=case_audit(df,{'101','102'},canonical_case_id)
        self.assertEqual(a.Casos_em_falta.tolist(),['102','101'])
    def test_duplicate_case_alias_rejected(self):
        df=pd.DataFrame([dict(panel=1,node=2,case='101 (C)'),dict(panel=1,node=2,case='101')])
        with self.assertRaises(ValueError): case_audit(df,{'101'},canonical_case_id)
    def test_incomplete_is_in_summary(self):
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101-102',qp_case='302',wk_check_enabled=True,axial_convention='Tracção positiva')
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=2,case=c,mxx=10,myy=1,mxy=0,nxx=0,nyy=0,nxy=0,qxx=0,qyy=0) for c in [101,302]]))
        r=d.design_dataframe(df)
        self.assertEqual(r.Case_missing.tolist(),['102','102'])
        self.assertIn('cobertura de combinações incompleta',WallsEC2App.panel_outcome(r)[1])
