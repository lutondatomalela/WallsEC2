import copy,tempfile,unittest
from pathlib import Path
from wall_reference_comparison import *

class ReferenceComparison(unittest.TestCase):
    def setUp(self):
        inp=dict(project='S',panel='1',node='2',case='302 (C)',role='ELS-QP',forces=dict.fromkeys(FORCES,0.),mesh=dict.fromkeys(('X+','X-','Y+','Y-'),'Ø12//200'),h_mm=250.,cover_mm=30.,fck_MPa=30.,fyk_MPa=500.)
        self.request=make_request([dict(inputs=inp,internal_experimental={'wk_plus_mm':.2,'wk_minus_mm':None})])
        self.response=blank_response(self.request);self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.report=Path(self.temp.name)/'report.txt';self.report.write_text('Synthetic, not structural validation')
        self.response.update(responsavel='test',metodo='synthetic',relatorio_sha256=hashlib.sha256(self.report.read_bytes()).hexdigest())
        self.response['rows'][0].update(equivalence_confirmed=True,reference={'wk_plus_mm':.25,'wk_minus_mm':0.})
    def test_numeric(self):
        a,b=compare(self.request,self.response,self.report);self.assertAlmostEqual(a['difference'],-.05);self.assertAlmostEqual(a['relative_difference'],-.2);self.assertIsNone(b['difference']);self.assertNotIn('Conforme',a['status'])
    def test_equivalence(self):
        self.response['rows'][0]['equivalence_confirmed']=False
        self.assertTrue(all(r['difference'] is None for r in compare(self.request,self.response,self.report)))
    def test_changed_forces(self):
        self.request['rows'][0]['inputs']['forces']['Qx']=1.
        with self.assertRaises(ValueError):compare(self.request,self.response,self.report)
    def test_missing_row(self):
        self.response['rows']=[]
        with self.assertRaises(ValueError):compare(self.request,self.response,self.report)
    def test_report_changed(self):
        self.report.write_text('other')
        with self.assertRaises(ValueError):compare(self.request,self.response,self.report)
    def test_invalid_reference(self):
        for v in (-1,float('nan'),True):
            self.response['rows'][0]['reference']['wk_plus_mm']=v
            with self.assertRaises(ValueError):compare(self.request,self.response,self.report)
    def test_zero_reference(self):
        self.response['rows'][0]['reference']['wk_plus_mm']=0.
        a=compare(self.request,self.response,self.report)[0];self.assertEqual(a['difference'],.2);self.assertIsNone(a['relative_difference'])
