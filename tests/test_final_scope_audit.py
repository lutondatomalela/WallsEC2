import unittest
import numpy as np
import pandas as pd
from WallsEC2 import WallDesigner,WallsEC2App,clean_dataframe
from wall_physical_layers import elastic_trial,layout
from wall_elastic_shear_history import screen

class FinalScopeAudit(unittest.TestCase):
    def test_bound_tightening_preserves_sampled_upper_bound(self):
        fam=layout(250,30,[[(1,12,200)]]*4)
        n=np.array([[10.,-80.,12.],[30.,30.,5.]])
        m=np.array([[5.,-5.,3.],[1.,1.,1.]])
        q=np.array([[25.,20.],[0.,15.]])
        strain,p,_=elastic_trial(250,n,m,fam,33000.)
        old=np.maximum(0,p[:,:,1].max(axis=1))+1.5*np.linalg.norm(q,axis=1)/250
        new=screen(250,strain,q,33000.,intervals=32).tensile_upper_mpa.max(axis=1)
        actual=screen(250,strain,q,33000.,intervals=512).tensile_sample_mpa.max(axis=1)
        self.assertTrue(np.all(np.minimum(old,new)>=actual-1e-10))
        self.assertTrue(np.any(new<old))
    def test_seccional_not_global_and_no_fake_wk(self):
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',wk_check_enabled=True,axial_convention='Tracção positiva',effective_length_mm=2000,creep_effective=1.5)
        d.sandwich_design=True
        data=[dict(panel=1,node=1,case=c,nxx=-5,nyy=-5,nxy=1,mxx=.1,myy=.1,mxy=.02,qxx=.1,qyy=.1) for c in (101,302,303,311)]
        r=d.design_dataframe(clean_dataframe(pd.DataFrame(data)))
        state,why=WallsEC2App.panel_outcome(r)
        self.assertEqual(state,'OK*');self.assertNotIn('global',why)
        self.assertTrue(r.loc[r.Combo_type.eq('ELS-QP'),'wk_max_mm'].isna().all())
        mask=r.Combo_type.eq('ELU')
        r.loc[mask,'Sand_intact_candidate']=False
        r.loc[mask,'Sand_status']='Modelo sandwich não satisfeito no limite de triagem; 6.109 não demonstrado'
        r.loc[mask,'Sand_util']=1.4
        self.assertEqual(WallsEC2App.panel_outcome(r)[0],'Incompleto')
        r.loc[mask,'util_M']=1.1
        self.assertEqual(WallsEC2App.panel_outcome(r)[0],'Não conforme')
