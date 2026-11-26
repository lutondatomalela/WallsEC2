import math
import unittest

from shell_crack_detail import (OrthogonalFace, crack_spacing_orthogonal,
                                projected_tension_band as band, relative_mean_strain)


class ShellCrackDetailTests(unittest.TestCase):
    def test_geometry_unequal_bars_and_mirror(self):
        face = OrthogonalFace(1, 40, 12, 16, 150, 200, 2)
        x, y = face.layers(250, 1)
        self.assertEqual((x.z_mm, y.z_mm), (61, 77))
        self.assertAlmostEqual(x.area_mm2_m, 240*math.pi)
        self.assertEqual(face.layers(250, -1)[0].z_mm, -x.z_mm)
        with self.assertRaises(ValueError):
            face.layers(130, 1)

    def test_equal_spacing_at_45_degrees(self):
        self.assertAlmostEqual(crack_spacing_orthogonal(300, 300, math.pi/4), 300/math.sqrt(2))

    def test_rotation_preserves_spacing(self):
        theta = math.radians(32)
        self.assertAlmostEqual(crack_spacing_orthogonal(220, 400, theta),
                               crack_spacing_orthogonal(400, 220, math.pi/2-theta))
        self.assertEqual(crack_spacing_orthogonal(220, 400, math.radians(10)), 220)
        self.assertEqual(crack_spacing_orthogonal(220, 400, math.radians(80)), 400)

    def test_relative_strain_bound_and_main_expression(self):
        self.assertAlmostEqual(relative_mean_strain(100, 200000, 30000, .01, 3), .0003)
        self.assertAlmostEqual(relative_mean_strain(300, 200000, 30000, .02, 3), .00116)


class ProjectedTensionBandTests(unittest.TestCase):
    def test_pure_flexure_and_reversed_face(self):
        a = band(240, (0, 0, 0), (1e-5, 0, 0), 1, 0, 35)
        self.assertEqual(a.tension_depth_mm, 120)
        self.assertEqual(a.candidate_depth_mm, 40)
        self.assertTrue(a.contains_bar_axis)
        self.assertEqual(band(240, (0, 0, 0), (1e-5, 0, 0), -1, 0, 35).candidate_depth_mm, 0)
        self.assertEqual(band(240, (0, 0, 0), (-1e-5, 0, 0), -1, 0, 35), a)

    def test_projected_membrane_shear(self):
        a = band(240, (0, 0, .001), (0, 0, 0), 1, math.pi/4, 35)
        self.assertAlmostEqual(a.face_strain, .001)
        self.assertEqual(a.tension_depth_mm, 240)
        self.assertEqual(a.candidate_depth_mm, 87.5)
        self.assertEqual(band(240, (0, 0, .001), (0, 0, 0), 1, -math.pi/4, 35).candidate_depth_mm, 0)

    def test_thin_band_does_not_credit_deep_bar(self):
        a = band(240, (-.0006, 0, 0), (1e-5, 0, 0), 1, 0, 30)
        self.assertAlmostEqual(a.tension_depth_mm, 60)
        self.assertAlmostEqual(a.candidate_depth_mm, 20)
        self.assertFalse(a.contains_bar_axis)


class CrackJumpTests(unittest.TestCase):
    def test_opening_and_slip_at_arbitrary_angle(self):
        from shell_crack_detail import recover_crack_jump
        theta, spacing, w, slip = .61, 200., .3, -.12
        n = (math.cos(theta), math.sin(theta))
        t = (-n[1], n[0])
        jump = [w*a + slip*b for a, b in zip(n, t)]
        e = [(jump[i]*n[j]+jump[j]*n[i])/(2*spacing) for i, j in ((0, 0), (1, 1), (0, 1))]
        for direction in (theta, theta+math.pi):
            r = recover_crack_jump(e, direction, spacing)
            self.assertAlmostEqual(r.opening_mm, w)
            self.assertAlmostEqual(r.slip_mm, slip)

    def test_independent_shear_is_required(self):
        from shell_crack_detail import recover_crack_jump
        # Same X/Y readings, but changing the relative shear changes opening.
        a = recover_crack_jump((.001, .001, .001), math.pi/4, 150)
        self.assertAlmostEqual(a.opening_mm, .3)
        with self.assertRaisesRegex(ValueError, "incompatíveis"):
            recover_crack_jump((.001, .001, 0), math.pi/4, 150)
        with self.assertRaises(ValueError):
            recover_crack_jump((.001, .001), math.pi/4, 150)

    def test_aligned_and_closed(self):
        from shell_crack_detail import recover_crack_jump
        r = recover_crack_jump((.001, 0, 0), 0, 250)
        self.assertAlmostEqual(r.opening_mm, .25)
        self.assertEqual(r.slip_mm, 0)
        with self.assertRaisesRegex(ValueError, "negativo"):
            recover_crack_jump((-.001, 0, 0), 0, 250)
