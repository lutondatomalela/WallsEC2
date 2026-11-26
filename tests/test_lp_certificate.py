import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from wall_lp_certificate import certify
from wall_physical_layers import PhysicalCapacity,layout
from wall_adaptive_capacity import solve

class PrimalTests(unittest.TestCase):
    def test_constraints_independent(self):
        eq=[[1.,1.]];ub=[[1.,0.]];bounds=[(0.,2.),(0.,2.)]
        for x,b,cap,valid in [([1.,1.],[2.],[1.],True),([1.,1.],[3.],[1.],False),([1.,1.],[2.],[.5],False),([-1.,1.],[0.],[1.],False),([3.,1.],[4.],[3.],False),([np.nan,1.],[0.],[1.],False)]:
            self.assertEqual(certify(x,eq,b,ub,cap,bounds).valid,valid)
    def test_invalid_point_is_not_resistance(self):
        model=PhysicalCapacity(250,layout(250,30,[[(1,12,200)]]*4),435,10)
        # Construct exact equilibrium at a deliberately excessive steel force.
        x=np.zeros(len(model.bounds)); x[model.nc]=10000; x[model.nc+1]=10000; x[-1]=1
        forces=model.matrix@x[:-1]; n=forces[:3];m=forces[3:]*model.h/2000
        with patch('wall_physical_layers.linprog',return_value=SimpleNamespace(success=True,x=x)):
            u,res,status=model.check(n,m)
        self.assertTrue(np.isnan(u)); self.assertLess(res,1e-6); self.assertIn('primal inválido',status)
        with patch('wall_adaptive_capacity.linprog',return_value=SimpleNamespace(success=True,x=x)):
            a=solve(model,n,m)
        self.assertFalse(a.converged);self.assertTrue(np.isnan(a.util))
    def test_real_point(self):
        model=PhysicalCapacity(250,layout(250,30,[[(1,12,200)]]*4),435,10)
        u,res,status=model.check([100,0,0],[0,0,0]);self.assertTrue(np.isfinite(u));self.assertLess(res,1e-6)
