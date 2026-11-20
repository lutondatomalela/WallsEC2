import tempfile
import unittest
from pathlib import Path
import pandas as pd
from WallsEC2 import clean_dataframe,read_csv_robust,combine_effort_tables,WallDesigner

RAW='Panel/Node/Case;MXX (kNm/m);MYY (kNm/m);MXY (kNm/m);NXX (kN/m);NYY (kN/m);NXY (kN/m)\n18/ 15936/ 101 (C);50,31;67,45;-17,61;309,30;-279,13;-7,32\n18/ 15937/ 101 (C);3,20;6,50;-6,93;276,50;-319,30;35,27\n'
WA='Panel/Node/Case;MXX+ (W&A) (kNm/m);MXX- (W&A) (kNm/m);MYY+ (W&A) (kNm/m);MYY- (W&A) (kNm/m);NMises (kN/m)\n18/ 15936/ 101 (C);67,92;0;85,06;0;509,98\n18/ 15937/ 101 (C);10,13;3,73;13,43;0;520,00\n'

class FormatTests(unittest.TestCase):
    def read(self,text,encoding='utf-16'):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'input.csv';p.write_text(text,encoding=encoding)
            return read_csv_robust(str(p))

    def test_utf16_export(self):
        d=clean_dataframe(self.read(RAW))
        self.assertEqual(len(d),2)
        self.assertEqual(d.iloc[0]['panel'],'18')
        self.assertEqual(d.iloc[0]['node'],'15936')
        self.assertAlmostEqual(d.iloc[0]['mxy'],-17.61)
        self.assertAlmostEqual(d.iloc[0]['nxx'],309.3)

    def test_utf16_big_endian(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'input.csv';p.write_bytes(b'\xfe\xff'+RAW.encode('utf-16-be'))
            self.assertEqual(len(read_csv_robust(str(p))),2)

    def test_utf8_and_cp1252(self):
        for enc in ['utf-8-sig','cp1252']:
            self.assertEqual(len(self.read(RAW,enc)),2)

    def test_wa_preserves_nmises(self):
        d=clean_dataframe(self.read(WA))
        self.assertAlmostEqual(d.iloc[0]['nmises'],509.98)
        self.assertFalse(d.iloc[0]['__missing_mxx_pos_wa'])
        self.assertTrue(d.iloc[0]['__missing_nxx'])
        self.assertAlmostEqual(d.iloc[0]['mxx_pos_wa'],67.92)

    def test_merge_is_by_key(self):
        raw=self.read(RAW);wa=self.read(WA).iloc[::-1]
        d=clean_dataframe(combine_effort_tables([raw,wa]))
        self.assertEqual(len(d),2)
        self.assertEqual(d.iloc[0]['node'],'15936')
        self.assertAlmostEqual(d.iloc[0]['mxx'],50.31)
        self.assertAlmostEqual(d.iloc[0]['mxx_pos_wa'],67.92)
        self.assertAlmostEqual(d.iloc[0]['nyy'],-279.13)
        self.assertEqual(d.iloc[0]['source_tables_count'],2)

    def test_no_double_wood_armer(self):
        d=clean_dataframe(combine_effort_tables([self.read(RAW),self.read(WA)]))
        r=WallDesigner(250,35,'C30/37',500).design_one(d.iloc[0])
        self.assertAlmostEqual(r['Mx+_WA'],67.92)
        self.assertAlmostEqual(r['My+_WA'],85.06)
        self.assertAlmostEqual(r['NXX_kN_m'],309.30)
        self.assertAlmostEqual(r['NMises_kN_m'],509.98)
        self.assertIn('não substitui',r['NMises_usage'])
        self.assertEqual(r['Source_tables_count'],2)

    def test_nmises_does_not_become_axial(self):
        d=clean_dataframe(self.read(WA))
        r=WallDesigner(250,35,'C30/37',500).design_one(d.iloc[0])
        self.assertEqual(r['NXX_kN_m'],0)
        self.assertIn('NMises é informativo',r['Verification_reason'])
        self.assertEqual(r['Status'],'Verificar')

    def test_mismatch_rejected(self):
        raw=self.read(RAW);wa=self.read(WA).iloc[:1]
        with self.assertRaisesRegex(ValueError,'não coincidentes'):
            combine_effort_tables([raw,wa])

    def test_duplicates_rejected(self):
        raw=self.read(RAW)
        with self.assertRaisesRegex(ValueError,'duplicadas'):
            combine_effort_tables([raw,pd.concat([raw,raw])])

    def test_conflicting_values_rejected(self):
        raw=self.read(RAW);other=raw.copy();other.iloc[0,1]='99'
        with self.assertRaisesRegex(ValueError,'conflito'):
            combine_effort_tables([raw,other])

    def test_incompatible_units_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unidades incompatíveis'):
            combine_effort_tables([self.read(RAW),self.read(WA.replace('kNm/m','Nm/m'))])

    def test_starred_nodes(self):
        d=clean_dataframe(self.read(RAW.replace('15936/','15936*/')))
        self.assertEqual(d.iloc[0]['node'],'15936')

if __name__=='__main__':unittest.main()
