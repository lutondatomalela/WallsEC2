import unittest
from tools.calcular_lote import derive


class BatchParameters(unittest.TestCase):
    def test_geometry_does_not_imply_creep(self):
        l0, phi, missing = derive(dict(altura_mm=3200, k=.75), "C30/37")
        self.assertEqual(l0, 2400)
        self.assertIsNone(phi)
        self.assertIn("razao_momentos", missing)

    def test_explicit_zero_is_not_missing(self):
        params = dict(altura_mm=3000,k=1,rh=75,h0_mm=250,idade_ajustada_dias=28,razao_momentos=0)
        self.assertEqual(derive(params,"C30/37"),(3000,0,[]))
        with self.assertRaises(ValueError):
            derive(dict(params,k=-1),"C30/37")
