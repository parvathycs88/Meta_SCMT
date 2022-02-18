'''design metasurface by modeling the meta unit as waveguide. 
    the coupling between waveguide is modeled by spacial couple mode theory (SCMT).
    note:
        the unit is [um].
        waveguide only has TE mode. (Ey, and Hx are non zero, other polarizations are zero.
        the wave propagation direction is z direction.
        the incident direction is within x-z plane.
        the incident angle theta is the angle between incident direction and the z direction.
        the 1D waveguide (slabs) modes are calculated analytically, only for quick idea validation.
        the 2D waveguide (square rod) modes are claculated numerically using Tidy3d.
        the forward and backward are implemented using pytorch.
        the number of waveguide for one side is N, for 1D, number of waveguides in metasurface is N; for 2D, N^2.
        the problem size is propotional to total_num_waveguides^3 * modes_within_each_waveguide.'''
import numpy as np
import os
from .modes1D import Gen_modes1D
from .fitting_neffs import Fitting_neffs
#from modes2D import gen_modes2D

class GP():
    def __init__(self,dim, modes, N, period, res, wh, prop_dis, lam, n_sub, n_wg, theta, h_min, h_max, dh, path = 'sim_cache/'):
        self.dim = dim #dim = 1 or 2.
        self.modes = modes #number of modes with in a single waveguide. modes <= 2 is usually good enough.
        self.C_EPSILON = 3 * 8.85 * 10**-4 # C * EPSILON
        self.Knnc = 2 #number of nearest neighbors for the C matrix.
        self.Knnk = 2 # for the K matrix.
        self.N = N
        self.Ni = N * 5 #the size of Cinv_stripped is (N**2 Ni). the size of A is roughly same with Cinv_stripped.
        self.k_row = N # generate C_inv_sub by k rows at same time.
        self.period = period
        self.res = res #resolution within one period
        self.wh = wh #waveguide height
        self.prop_dis = prop_dis #the propagate distance in free space.
        self.lam = lam
        self.k = 2 * np.pi / lam
        self.n_sub = n_sub #the refractive index of substrate.
        self.n_wg = n_wg# the refractive index of waveguide
        self.n0 = 1 #the refractive index of air.
        self.theta = theta #the incident angle.
        self.h_min = h_min #h_min and h_max define the range of the width of waveguide.
        self.h_max = h_max
        self.dh = dh #the step size of h.
        self.path = path #the inter state store path            
        if not os.path.exists(path):
            os.mkdir(path)
class Sim():
    def __init__(self,**keyword_args) -> None:
        self.GP = GP(**keyword_args)
        
        if self.GP.dim == 1:
            self.gen_modes = Gen_modes1D(self.GP)
            self.fitting_neffs = Fitting_neffs(self.GP.modes, self.gen_modes, self.GP.dh, self.GP.path)
            

        
            