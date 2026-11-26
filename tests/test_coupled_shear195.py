import unittest
import numpy as np
import pandas as pd
from wall_coupled_shear import truss_increment,assess,refine_resultant_mesh
from wall_physical_layers import layout,PhysicalCapacity
from wall_resultant_shear import resultant_shear
from WallsEC2 import WallDesigner

class CoupledShear(unittest.TestCase):
    def setUp(self):
        self.f=layout(250,30,[[(1,12,200)]]*4)
        self.d=WallDesigner(250,30,'C30/37',500,axial_convention='Tracção positiva',optimize_rebar=True,base_vertical_phi=12,base_horizontal_phi=12)
        self.d.shell_qp_diagnostic=True
    def test_increment_equilibrium(self):
        np.testing.assert_allclose(truss_increment([[30,40],[-30,40],[0,0]],2),[[36,64,48],[36,64,-48],[0,0,0]])
        with self.assertRaises(ValueError):truss_increment([30,40],3)
    def test_credit_cap(self):
        for n in [-200.,-1000.,-5000.]:
            fcd=self.d.cp['fcd'];a=resultant_shear(250,self.f,[[n,0,0]],[[100,0]],30,fcd,1.5,compression_credit=True)
            sig=min(-n/250,.2*fcd)
            self.assertAlmostEqual(a['PhysShear_sigma_cp_MPa'][0],sig)
            d=a['PhysShear_d_mm'][0];area=1000*np.pi*12**2/4/200
            self.assertAlmostEqual(a['PhysShear_VRdc_kN_m'][0],self.d.shear_vrdc_kN_per_m(area,d,sig))
    def test_proposal_includes_tensile_tensor(self):
        class Model:
            def check(self,n,m):
                np.testing.assert_allclose(n,[96,64,-48]);np.testing.assert_allclose(m,[1,2,3]);return .8,0,'equilibrio'
        r=assess(250,self.f,[[-32,-8,48.]],[[1,2,3]],[[160,-120]],30,20,1.5,500,435,Model())
        self.assertGreater(r['PhysLL_Asw_req_mm2_m2'][0],0)
        self.assertIn('não instalada',r['PhysLL_status'][0]);self.assertEqual(r['PhysLL_Face_util_com_trelica'][0],.8)
    def test_missing_not_pass(self):
        m=PhysicalCapacity(250,self.f,435,10.)
        r=assess(250,self.f,[[0,0,0]],[[0,0,0]],[[np.nan,0]],30,20,1.5,500,435,m)
        self.assertTrue(np.isnan(r['PhysLL_util'][0]));self.assertEqual(r['PhysLL_status'][0],'Dados insuficientes')
    def test_refinement(self):
        a=self.d.rebar_from_phi_spacing(12,200);g=pd.DataFrame(dict(Panel=['1'],tensor_ok=[True],shear_ok=[True],NXX=[0.],NYY=[0.],NXY=[0.],QXX=[85.],QYY=[85.]))
        orig=[a]*4;ad={'1':orig};refine_resultant_mesh(self.d,g,ad);mesh=ad['1']
        fam=layout(250,30,[self.d._parse_rebar_text(v.text) for v in mesh]);r=resultant_shear(250,fam,[[0,0,0]],[[85,85]],30,self.d.cp['fcd'],self.d.gamma_c,compression_credit=True)
        self.assertLessEqual(r['PhysShear_util'][0],1+1e-7);self.assertTrue(all(v.as_prov>=a.as_prov for v in mesh));self.assertGreater(sum(v.as_prov for v in mesh),4*a.as_prov)
