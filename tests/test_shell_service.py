import unittest

import numpy as np

from wall_shell_service import BarLayer, solve_cracked_shell


class ShellServiceTests(unittest.TestCase):
    bars = [BarLayer(i, z, 1000.) for i in (0, 1) for z in (60., -60.)]

    def test_biaxial_tension_by_steel_only(self):
        r = solve_cracked_shell(200, (200, 100, 0), (0, 0, 0), self.bars, 30000)
        np.testing.assert_allclose(r.steel_stress_mpa, [100, 100, 50, 50], atol=1e-5)
        self.assertLess(r.residual_mpa, 1e-8)

    def test_compressive_shear_and_twist(self):
        h, ec, nf = 200., 30000., 48
        r = solve_cracked_shell(h, (-1000, -1000, 100), (0, 0, 10), self.bars, ec, fibres=nf)
        self.assertAlmostEqual(r.mid_strain[2], 100/(h*ec), places=11)
        inertia = h**3/12*(1-1/nf**2)
        self.assertAlmostEqual(r.curvature_per_mm[2], 10*1000/(ec*inertia), places=12)
        self.assertTrue((r.face_principal_strain < 0).all())

    def test_membrane_shear_cracks_45_degrees(self):
        h, ec, nxy = 200., 30000., 100.
        r = solve_cracked_shell(h, (0, 0, nxy), (0, 0, 0), self.bars, ec)
        np.testing.assert_allclose(r.steel_stress_mpa, [50]*4, atol=1e-5)
        np.testing.assert_allclose(r.face_principal_strain[:, 0], -2*nxy/(h*ec), atol=1e-10)
        self.assertGreater(r.face_principal_strain[0, 1], 0)

    def test_non_equilibrating_layout_returns_no_result(self):
        self.assertIsNone(solve_cracked_shell(200, (0, 0, 100), (0, 0, 0), (), 30000))
