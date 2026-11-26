import unittest
import numpy as np
from wall_compatible_ultimate import compatible_equilibrium
from wall_physical_layers import layout,crack_candidate

class CompatibleTests(unittest.TestCase):
    def setUp(self):
        self.b=[f.bar for f in layout(250,30,[[(1,12,200)]]*4)]
    def solve(self,n,m,**kw):
        return compatible_equilibrium(250,n,m,self.b,10.56,500/1.15,**kw)
    def test_pure_tension_exact(self):
        r=self.solve([100,0,0],[0,0,0]); a=sum(b.area_mm2_m for b in self.b if b.axis==0)
        self.assertLess(r.residual_mpa,1e-7);self.assertAlmostEqual(r.steel_stress_max,100000/a,places=5);self.assertLess(r.concrete_strain,1e-9) # < 1 nanostrain; residual and analytical steel stress checked separately
    def test_compression_steel(self):
        r=self.solve([-1000,0,0],[0,0,0]);self.assertLess(r.residual_mpa,1e-7); self.assertGreater(r.steel_stress_max,0);self.assertLess(r.strain_ratio,1)
    def test_reflection(self):
        a=self.solve([-200,-100,55],[5,-10,9]);b=self.solve([-200,-100,-55],[5,-10,-9]);self.assertLess(a.residual_mpa,1e-7);self.assertLess(b.residual_mpa,1e-7);self.assertAlmostEqual(a.strain_ratio,b.strain_ratio,places=7)
    def test_excessive_tension(self):
        r=self.solve([10000,0,0],[0,0,0]); self.assertIn('Sem equilíbrio',r.status)
    def test_critical_pc1(self):
        f=layout(250,30,[[(1,12,200),(1,20,200)],[(1,12,200),(1,10,200)],[(1,12,200),(2,16,200)],[(1,12,200),(1,20,200)]])
        a=compatible_equilibrium(250,[-148.94,-1153.56,440.81],[9.08,49.9,.57],[x.bar for x in f],10.56,500/1.15)
        self.assertLess(a.residual_mpa,1e-6);self.assertGreater(a.compression_ratio,0)
    def test_dense_families_net_concrete(self):
        bars=[f.bar for f in layout(220,30,[[(1,12,200),(3,20,200)]]*4)]
        e=.0005;fc=10.56;es=200000.;a=sum(b.area_mm2_m for b in bars)/1000
        ax=sum(b.area_mm2_m for b in bars if b.axis==0)/1000
        n=-((220-a)*fc*(2*e/.002-(e/.002)**2)+ax*es*e)
        for fibres in (24,48,96):
            r=compatible_equilibrium(220,[n,0,0],[0,0,0],bars,fc,500/1.15,fibres=fibres)
            self.assertAlmostEqual(r.concrete_strain,e,places=10)
            self.assertLess(r.residual_mpa,1e-7)
    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):self.solve([float('nan'),0,0],[0,0,0])
    def test_crack_candidate_trace(self):
        f=layout(250,30,[[(1,12,200)]]*4)
        r=crack_candidate(250,f,[100,200,0],[0,0,0],10000,2.9,ec_reference=30000)
        self.assertGreater(r['PhysQP_surface_tensile_strain_plus'],0);self.assertNotIn('wk_max_mm',r)

class DesignCorrections(unittest.TestCase):
    def test_horizontal_minimum_tracks_vertical(self):
        from WallsEC2 import WallDesigner
        for vertical_y in (True,False):
            d=WallDesigner(250,30,'C30/37',500,local_y_is_vertical=vertical_y,phi_max_mm=20)
            v=2 if vertical_y else 0;h=2-v
            mesh=[d.choose_rebar(250,400) for _ in range(4)]
            mesh[v]=d.choose_rebar(3000,400);mesh[v+1]=d.choose_rebar(3000,400)
            before=[m.as_prov for m in mesh]
            d.enforce_horizontal_minimum(mesh)
            self.assertGreaterEqual(mesh[h].as_prov+mesh[h+1].as_prov,.25*(mesh[v].as_prov+mesh[v+1].as_prov)-1e-8)
            self.assertEqual(mesh[v].as_prov,before[v]);self.assertEqual(mesh[v+1].as_prov,before[v+1]);self.assertTrue(all(m.as_prov>=a for m,a in zip(mesh,before)))
    def test_car_uses_instantaneous_modulus(self):
        from WallsEC2 import WallDesigner,clean_dataframe
        import pandas as pd
        rows=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,nxx=-100,nyy=20,nxy=0,mxx=10,myy=5,mxy=0,qxx=0,qyy=0) for c in (101,302,303,311)]))
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',axial_convention='Tracção positiva',creep_effective=2)
        mesh=[d.choose_rebar(1200,200) for _ in range(4)]
        a=d.design_one(rows.iloc[2],mesh);d.creep_effective=0;b=d.design_one(rows.iloc[2],mesh)
        self.assertAlmostEqual(a['ELS_X_sigma_plus_MPa'],b['ELS_X_sigma_plus_MPa'])
    def test_service_history_and_critical_audit(self):
        from WallsEC2 import WallDesigner,clean_dataframe
        import pandas as pd
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',axial_convention='Tracção positiva',wk_check_enabled=True)
        d.shell_qp_diagnostic=True
        r=d.design_dataframe(clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,nxx=-20,nyy=30,nxy=5,mxx=10,myy=5,mxy=1,qxx=0,qyy=0) for c in (101,302,303,311)])))
        self.assertIn('experimental',r.iloc[0].PhysCompat_status)
        self.assertIn('ELS importado',r.iloc[1].PhysHistory_status)
        self.assertTrue(np.isnan(r.iloc[1].wk_max_mm))
    def test_compatible_compression_manufactured(self):
        # Independently obtain a uniform uniaxial load from the constitutive laws.
        b=[f.bar for f in layout(250,30,[[(1,12,200)]]*4)]
        e=.0005; fc=10.56; es=200000.;fyd=500/1.15
        ac=250-sum(x.area_mm2_m for x in b)/1000
        asx=sum(x.area_mm2_m for x in b if x.axis==0)/1000
        n=-(ac*fc*(2*e/.002-(e/.002)**2)+asx*es*e)
        r=compatible_equilibrium(250,[n,0,0],[0,0,0],b,fc,fyd)
        self.assertAlmostEqual(r.concrete_strain,e,places=10)
        self.assertAlmostEqual(r.steel_stress_max,es*e,places=5)
        self.assertLess(r.residual_mpa,1e-7)
