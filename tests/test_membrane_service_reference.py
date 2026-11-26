import unittest
import numpy as np
from wall_membrane_service_reference import membrane_service
from wall_shell_service import solve_cracked_shell,BarLayer
from wall_physical_layers import layout
from wall_concrete_fibres import net_weights

class MembraneReferenceTests(unittest.TestCase):
    def test_pure_shear_analytic(self):
        r=membrane_service([0,0,100],200,2000,2000,30000)
        np.testing.assert_allclose(r.steel_stress,[50,50]);np.testing.assert_allclose(r.concrete_stress,[-100/196,-100/196,100/196])
    def test_random_membrane_vs_layer_solver(self):
        rng=np.random.default_rng(20261125)
        f=layout(250,30,[[(1,12,200)],[(1,12,200)],[(1,16,150)],[(1,16,150)]])
        bars=[a.bar for a in f];a=[sum(b.area_mm2_m for b in bars if b.axis==i) for i in (0,1)];w=net_weights(250,f)
        for n in rng.uniform([-800,-800,-200],[200,200,200],size=(100,3)):
            r=membrane_service(n,250,*a,30000);s=solve_cracked_shell(250,n,[0,0,0],bars,30000,concrete_weights=w)
            self.assertIsNotNone(s);np.testing.assert_allclose(s.mid_strain,r.strain,rtol=1e-5,atol=2e-9)
            np.testing.assert_allclose(s.steel_stress_mpa,[r.steel_stress[b.axis] for b in bars],rtol=1e-5,atol=4e-4)
            np.testing.assert_allclose(s.curvature_per_mm,0,atol=2e-11)
            # Independently integrate resultant equilibrium.
            recovered=r.concrete_stress*(250-sum(a)/1000);recovered[:2]+=np.array(a)*r.steel_stress/1000
            np.testing.assert_allclose(recovered,n,atol=1e-8)
    def test_sign_reflection(self):
        a=membrane_service([-200,50,80],250,1000,1500,30000);b=membrane_service([-200,50,-80],250,1000,1500,30000)
        np.testing.assert_allclose(a.strain,b.strain*[1,1,-1]);np.testing.assert_allclose(a.steel_stress,b.steel_stress)
