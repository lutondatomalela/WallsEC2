import math
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import numpy as np
from wall_geometry import panel_geometry, read_nodes


class PanelGeometryTests(unittest.TestCase):
    def test_rotated_and_inclined(self):
        for a in (.2,1.1,2.3):
            for tilt in (0,.45):
                u=np.array([math.cos(a),math.sin(a),0])
                v=np.array([-u[1]*math.sin(tilt), u[0]*math.sin(tilt),math.cos(tilt)])
                nodes={str(i):(* (np.array([50,-30,120])+w*u+h*v), '') for i,(w,h) in enumerate([(0,0),(4,0),(2,2),(0,3),(4,3)])}
                g=panel_geometry(nodes,nodes)
                self.assertAlmostEqual(g['altura_no_plano_m'],3)
                self.assertAlmostEqual(g['largura_horizontal_no_plano_m'],4)
                self.assertAlmostEqual(g['desnivel_m'],3*math.cos(tilt))
                self.assertAlmostEqual(g['azimute_largura_desde_X_graus'],math.degrees(a))

    def test_ineligible_clouds(self):
        for coords in ([(0,0,0),(0,1,0),(1,1,0)],[(0,0,0),(0,0,1),(0,0,2)],[(0,0,0),(0,1,0),(1,0,1),(2,1,0)]):
            nodes={str(i):(*p,'') for i,p in enumerate(coords)}
            self.assertNotIn('altura_no_plano_m',panel_geometry(nodes,nodes))
            self.assertNotIn('altura_no_plano_m',panel_geometry([*nodes,99],nodes))

    def test_units_and_duplicate(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'n.csv'
            s='Node;X (mm);Y (m);Z (cm);Support\n 1;100;2,5;300;Fixed\n'
            p.write_text(s+'*;;;;\n',encoding='utf-16')
            self.assertEqual(read_nodes(p)['1'],(.1,2.5,3,'Fixed'))
            p.write_text(s+'1;100;2,5;300;Fixed\n',encoding='utf-16')
            with self.assertRaises(ValueError): read_nodes(p)

class RestraintTests(unittest.TestCase):
    def test_rotated_inclined_bays(self):
        from wall_geometry import confirmed_restraint_spacing
        for a in (.2,1.2,2.5):
            u=np.array([math.cos(a),math.sin(a),0]); v=np.array([-u[1]*.6,u[0]*.6,.8])
            nodes={str(i+1):(*(np.array([20,50,100])+x*u+y*v),'') for i,(x,y) in enumerate([(0,0),(4,0),(0,2),(4,2),(0,5),(4,5)])}
            lines=[dict(nos_extremos=[i,i+1],justificacao='Laje confirmada') for i in (1,3,5)]
            r=confirmed_restraint_spacing(nodes,nodes,lines)
            self.assertAlmostEqual(r['altura_mm'],3000)
            np.testing.assert_allclose(r['distancias_mm'],[2000,3000])
            with self.assertRaises(ValueError): confirmed_restraint_spacing(nodes,nodes,lines[1:])
            with self.assertRaises(ValueError): confirmed_restraint_spacing(nodes,nodes,[lines[0],dict(nos_extremos=[3,6],justificacao='a'),lines[2]])
            with self.assertRaises(ValueError): confirmed_restraint_spacing(nodes,nodes,[lines[0],lines[0],lines[2]])
            with self.assertRaises(ValueError): confirmed_restraint_spacing(nodes,nodes,[lines[0],dict(nos_extremos=[3,4],justificacao=''),lines[2]])
