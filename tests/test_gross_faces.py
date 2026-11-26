import unittest
from wall_section import gross_face_principal

class FaceStressTests(unittest.TestCase):
    def test_pure_shear(self):
        for hi, lo, angle in gross_face_principal(200,(0,0,200),(0,0,0)):
            self.assertEqual((hi,lo,angle),(1,-1,45))

    def test_twist_reverses_face_direction(self):
        self.assertEqual(gross_face_principal(200,(0,0,0),(0,0,20)),
                         ((3,-3,45),(3,-3,-45)))

    def test_axial_and_bending(self):
        a,b=gross_face_principal(200,(200,0,0),(20,0,0))
        self.assertEqual(a,(4,0,0))
        self.assertEqual(b,(0,-2,90))
