import unittest
import numpy as np
from wall_sandwich_design import intact_ll_bound

class IntactLL(unittest.TestCase):
    def test_zero_and_tension(self):
        n=np.array([[0,0,0],[400,0,0]],float);m=np.zeros_like(n);q=np.zeros((2,2))
        r=intact_ll_bound(200,n,m,q,30,20,1.5)
        self.assertEqual(r['intact_phi_upper'][0],-1.)
        self.assertTrue(r['intact_candidate'][0]);self.assertFalse(r['intact_candidate'][1])
    def test_high_shear_and_bending(self):
        r=intact_ll_bound(200,np.zeros((2,3)),[[100,0,0],[0,0,0]],[[0,0],[1000,0]],30,20,1.5)
        self.assertFalse(r['intact_candidate'].any())
    def test_bound_against_independent_depth_sampling(self):
        rng=np.random.default_rng(42);n=rng.normal(0,100,(100,3));m=rng.normal(0,15,(100,3));q=rng.normal(0,50,(100,2));h=200
        r=intact_ll_bound(h,n,m,q,30,20,1.5);fcm=38.;k=.3*30**(2/3)/fcm
        alpha=1/(9*k**1.4);beta=1/(3.7*k**1.1);c1=1/(.7*k**.9);c2=1-6.8*(k-.07)**2
        for z in np.linspace(-1,1,101):
            x,y,t=(n/h+6000*m*z/h**2).T;a,b=(1.5*q/h*(1-z*z)).T
            S=np.zeros((100,3,3));S[:,0,0]=x;S[:,1,1]=y;S[:,0,1]=S[:,1,0]=t;S[:,0,2]=S[:,2,0]=a;S[:,1,2]=S[:,2,1]=b
            v=np.linalg.eigvalsh(S);dev=v-v.mean(axis=1)[:,None];j2=(dev**2).sum(axis=1)/2;j3=dev.prod(axis=1)
            c=np.clip(3*np.sqrt(3)/2*j3/np.maximum(j2,1e-30)**1.5,-1,1)
            lam=c1*np.cos(np.arccos(c2*c)/3)
            phi=alpha*j2/fcm**2+lam*np.sqrt(j2)/fcm+beta*v.sum(axis=1)/fcm-1
            self.assertTrue(np.all(phi<=r['intact_phi_upper']+1e-12))
            self.assertTrue(np.all(v[:,-1]<=r['intact_sigma_t_upper_MPa']+1e-12))
            self.assertTrue(np.all(-v[:,0]<=r['intact_sigma_c_upper_MPa']+1e-12))
