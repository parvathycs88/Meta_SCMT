import numpy as np
import torch
import torch.nn as nn
from ..utils import Model, fourier_conv1D
from .sputil_1D import gen_coo_sparse, gen_dis_CK_input, gen_input_hs
from scipy import special
from typing import List

class Metalayer(torch.nn.Module):
    def __init__(self, GP, COUPLING, N, inverse = False):
        '''

        '''
        super(Metalayer, self).__init__()
        self.COUPLING = COUPLING
        self.h_paras = torch.nn.Parameter(torch.empty((N,), dtype = torch.float))
        self.hs = None
        self.neffs = None
        self.GP = GP
        self.h_min = GP.h_min
        self.h_max = GP.h_max
        self.dh = GP.dh
        self.wh = GP.wh
        self.k = GP.k
        neff_paras = np.load(self.GP.path + "neff_paras.npy", allow_pickle= True)
        neff_paras = neff_paras.item()
        C_paras = np.load(self.GP.path + "C_paras.npy", allow_pickle= True)
        C_paras = C_paras.item()
        K_paras = np.load(self.GP.path + "K_paras.npy", allow_pickle= True)
        K_paras = K_paras.item()
        E_paras = np.load(self.GP.path + "E_paras.npy", allow_pickle= True)
        E_paras = E_paras.item()
        self.neffnn = gen_neff(GP.modes, neff_paras['nodes'], neff_paras['layers'])
        self.genc = gen_C(GP.modes, C_paras['nodes'], C_paras['layers'], N, GP.Knn)
        self.genk = gen_K(GP.modes, K_paras['nodes'], K_paras['layers'], N, GP.Knn)
        if inverse:
            self.genu0 = gen_U0(GP.modes, neff_paras['nodes'], neff_paras['layers'], E_paras['nodes'], E_paras['layers'], GP.res, N, GP.n0, GP.C_EPSILON, GP.dx, GP.Knn)
            self.genen = gen_En(GP.modes, GP.res, N, GP.n_sub, GP.C_EPSILON, GP.dx, GP.Knn)
        else:
            self.genu0 = gen_U0(GP.modes, neff_paras['nodes'], neff_paras['layers'], E_paras['nodes'], E_paras['layers'], GP.res, N, GP.n_sub, GP.C_EPSILON, GP.dx, GP.Knn)
            self.genen = gen_En(GP.modes, GP.res, N, GP.n0, GP.C_EPSILON, GP.dx, GP.Knn)
        self.sig = torch.nn.Sigmoid()
        self.gen_hs_input = gen_input_hs(N, GP.Knn)
        dis = torch.tensor(gen_dis_CK_input(N, GP.Knn), dtype = torch.float, requires_grad = False)
        self.register_buffer('dis', dis)
    def forward(self, E0):
        '''
        size of E0: (N + 2 * (Knnc + 1)) * period_resolution
        '''
        self.hs = self.sig(self.h_paras) * (self.h_max - self.h_min) + self.h_min
        #self.hs = torch.div(self.hs, self.GP.dh, rounding_mode = 'floor') * self.GP.dh
        self.neffs = self.neffnn(self.hs.view(-1, 1))
        with torch.set_grad_enabled(False):
            hs_no_grad = self.hs
            neffs_no_grad = self.neffs
        
        Eys, U0 = self.genu0(hs_no_grad, E0)
        if not self.COUPLING:
            P = torch.exp(self.neffs.view(-1,) * self.k * self.wh * 1j)
            Uz = P * U0 #shape [N*modes,]
        else:
            with torch.set_grad_enabled(False):
                hs_input = self.gen_hs_input(self.hs)
                CK_input = torch.cat([hs_input, self.dis],dim = -1)
                CK_input = CK_input.view(-1,3)
                C = self.genc(CK_input)
                K = self.genk(CK_input)
                C_inv = torch.inverse(C)
            B = torch.diag(self.neffs.view(-1,) * self.k)
            Eig_M = C_inv @ (B @ C + K)
            A = Eig_M * self.wh * 1j
            P = torch.matrix_exp(A) #waveguide propagator
            Uz = P @ U0

        En = self.genen(hs_no_grad, Uz, neffs_no_grad, Eys) #near field
        return En
    
    def reset(self, path):
        #nn.init_normal_(self.phase, 0, 0.02)
        torch.nn.init.constant_(self.h_paras, val = 0.0)
        self.neffnn.reset(path)
        self.genc.reset(path)
        self.genk.reset(path)
        self.genu0.reset(path)

class gen_neff(nn.Module):
    def __init__(self, modes, nodes, layers):
        super(gen_neff, self).__init__()    
        self.model = Model(in_size = 1, out_size = modes, layers = layers, nodes= nodes).requires_grad_(requires_grad=False)
    def forward(self, hs):
        '''
        input: 
            hs: array of waveguide widths [N,]
        output:
            neffs of each mode. shape: [N, number of modes for each waveguide.]
        '''
        return self.model(hs)
    def reset(self, path):
        model_state = torch.load(path + "fitting_neffs_state_dict")
        self.model.load_state_dict(model_state) 


class gen_U0(nn.Module):
    def __init__(self, modes, node_n, ln, node_e, le, res, N, n0, C_EPSILON, dx, Knn):
        super(gen_U0, self).__init__()
        self.N = N
        self.n0 = n0
        self.C_EPSILON = C_EPSILON
        self.dx = dx
        self.Knn = Knn
        self.modes = modes
        self.res = res
        self.neffnn = gen_neff(modes, node_n, ln).requires_grad_(requires_grad=False)
        enn_out_size = modes * 2 * (Knn + 1) * res
        self.Ey_size = 2 * (Knn + 1) * res
        self.enn = Model(1, enn_out_size, layers= le, nodes = node_e).requires_grad_(requires_grad=False)
        #self.register_buffer('E0_slice', torch.zeros((N, 1, self.Ey_size), dtype= torch.complex64))
    def forward(self, hs, E0):
        '''
        input:
            hs: array of waveguide widths [N,]
            E0: input field [(N +  2 * Knn + 1) * res,]
        output:
            neff: refractive index of each mode. shape [N, modes]
            T: modes amplitude coupled in. shape [N, number of modes]
        '''
        pad1 = ((2 * self.Knn + 1) * self.res)//2
        pad2 = (2 * self.Knn + 1) * self.res - pad1
        E0 = torch.nn.functional.pad(E0, pad = (pad1, pad2), mode='constant', value=0.0)
        neff = self.neffnn(hs.view(-1, 1))
        E0_slice = []
        for i in range(6):
            E0_slice.append(E0[i * self.res: (self.N + i) * self.res].view(self.N, 1, self.res))
        E0_slice = torch.cat(E0_slice, dim = -1)
        Ey = self.enn(hs.view(-1, 1))
        Ey = Ey.view(self.N, self.modes, self.Ey_size)
        E_sum = torch.sum(Ey * E0_slice, dim= -1, keepdim= False) # shape: [N, modes]
        eta = (neff * self.n0) / (neff + self.n0) #shape [N, modes]
        T = 2 * self.C_EPSILON * eta * E_sum * self.dx
        T = T.view(-1,)
        return Ey, T
    def reset(self, path):
        model_state = torch.load(path + "fitting_E_state_dict")
        self.enn.load_state_dict(model_state)
        self.neffnn.reset(path)

class gen_En(nn.Module):
    def __init__(self, modes, res, N, n0, C_EPSILON, dx, Knn):
        super(gen_En, self).__init__()
        self.N = N
        self.n0 = n0
        self.C_EPSILON = C_EPSILON
        self.dx = dx
        self.Knn = Knn
        self.modes = modes
        self.res = res
        self.Ey_size = 2 * (Knn + 1) * res
        self.total_size = (N + 2 * Knn + 1) * res
        self.register_buffer('En', torch.zeros((self.total_size,), dtype= torch.complex64))
    def forward(self, hs, U, neff, Ey):
        '''
            neff: shape [N, modes]
            Ey: shape [N, modes, fields]
        '''
        hs = hs.view(-1, 1)
        eta = (neff * self.n0) / (neff + self.n0) #shape: [N, modes]
        Ey = eta.view(-1, self.modes, 1) * Ey * U.view(-1, self.modes, 1)
        self.En = torch.zeros((self.total_size,), dtype= torch.complex64).to(hs.device)
        for i in range(self.N):
            for m in range(self.modes):
                temp_Ey = Ey[i, m]
                center = i * self.res + (self.Knn + 1) * self.res
                center = int(center)
                radius = int((self.Knn + 1) * self.res)
                self.En[center - radius: center + radius] += temp_Ey
        start = ((2 * self.Knn + 1) * self.res)//2
        end = start + self.N * self.res
        self.En = self.En[start:end]
        return self.En
        
class gen_C(nn.Module):
    def __init__(self, modes, node_c, lc, N, Knn):
        super(gen_C, self).__init__()
        self.channels = modes**2
        self.cnn = Model(3, self.channels, layers= lc, nodes = node_c).requires_grad_(requires_grad=False)
        coo = torch.tensor(gen_coo_sparse(N, Knn),dtype=int, requires_grad = False)
        self.register_buffer('coo', coo)
        self.N = N
        self.modes = modes 
        
    def forward(self, CK_inputs):
        '''
        input:
            CK_inputs: the cnn input is (hi, hj, dis), output is cij for all the channels.
            the CK_inputs includes all the possiable couplings for N waveguides. shape [N, 2 * (Knn + 1), 3]
        '''
        C_stripped = self.cnn(CK_inputs.view(-1, 3))
        C_sparses = []
        for mi in range(self.modes):
            for mj in range(self.modes):
                ch = mi * self.modes + mj
                val = C_stripped[:,ch]
                coo = self.coo * self.modes + torch.tensor(np.array([[mi], [mj]]), dtype = torch.int).to(self.coo.device)
                C_sparse = torch.sparse_coo_tensor(coo, val, (self.modes * self.N, self.modes * self.N), requires_grad= False)
                C_sparses.append(C_sparse)
        for C_temp in C_sparses[:-1]:
            C_sparse += C_temp
        C_sparse = C_sparse.coalesce()
        C_dense = C_sparse.to_dense()
        return C_dense
    def reset(self, path):
        model_state = torch.load(path + "fitting_C_state_dict")
        self.cnn.load_state_dict(model_state)

class gen_K(nn.Module):
    def __init__(self, modes, node_k, lk, N, Knn):
        super(gen_K, self).__init__()
        self.channels = modes**2
        self.knn = Model(3, self.channels, layers= lk, nodes = node_k).requires_grad_(requires_grad=False)
        coo = torch.tensor(gen_coo_sparse(N, Knn),dtype=int, requires_grad = False)
        self.register_buffer('coo', coo)
        self.N = N
        self.modes = modes 

    def forward(self, CK_inputs):
        '''
        input:
            CK_inputs: the cnn input is (hi, hj, dis), output is cij for all the channels.
            the CK_inputs includes all the possiable couplings for N waveguides. shape [N, 2 * (Knn + 1), 3]
        '''
        K_stripped = self.knn(CK_inputs.view(-1, 3))
        K_sparses = []
        for mi in range(self.modes):
            for mj in range(self.modes):
                ch = mi * self.modes + mj
                val = K_stripped[:,ch]
                coo = self.coo * self.modes + torch.tensor(np.array([[mi], [mj]]), dtype = torch.int).to(self.coo.device)
                K_sparse = torch.sparse_coo_tensor(coo, val, (self.modes * self.N, self.modes * self.N), requires_grad= False)
                K_sparses.append(K_sparse)
        for K_temp in K_sparses[:-1]:
            K_sparse += K_temp
        K_sparse = K_sparse.coalesce()
        K_dense = K_sparse.to_dense()
        return K_dense
    def reset(self, path):
        model_state = torch.load(path + "fitting_K_state_dict")
        self.knn.load_state_dict(model_state)

class SCMT_Model(nn.Module):
    def __init__(self, prop_dis, GP, COUPLING, N, inverse = False):
        super(SCMT_Model, self).__init__()

        self.prop = prop_dis
        total_size = (N) * GP.res
        self.metalayer1 = Metalayer(GP, COUPLING, N, inverse)
        if inverse:
            self.freelayer1 = freespace_layer(self.prop, GP.lam/GP.n_sub, total_size, GP.dx)
        else:
            self.freelayer1 = freespace_layer(self.prop, GP.lam, total_size, GP.dx)
    def forward(self, E0):
        En = self.metalayer1(E0)
        Ef = self.freelayer1(En)
        #If = torch.abs(Ef)**2
        #If = If/If.max()
        return Ef
    def reset(self, path):
        self.metalayer1.reset(path)
  
           
class SCMT_Model_2_layer(nn.Module):
    def __init__(self, prop_dis: List[float], GP, COUPLING, N, near_field=True):
        super(SCMT_Model_2_layer, self).__init__()
        '''
            the pillars are fabed on two side of the substrate. So that the light incident from air to sub then to air.
        '''
        SCMT_models = []
        self.prop_dis = prop_dis
        assert len(self.prop_dis) == 2, "2 layer model, number of prop_dis should be 2.!"
        SCMT_models.append(
            SCMT_Model(self.prop_dis[0], GP, COUPLING, N, inverse = True))
        SCMT_models.append(
            SCMT_Model(self.prop_dis[1], GP, COUPLING, N))
        self.SCMT_models = nn.ModuleList(SCMT_models)
        
    def forward(self, E0):
        Ei = E0
        for _, SCMT_model in enumerate(self.SCMT_models):
            Ei = SCMT_model(Ei)
        return Ei
    
    def reset(self, path):
        for i in range(len(self.prop_dis)):
            self.SCMT_models[i].reset(path)

class freespace_layer(nn.Module):
    def __init__(self, prop, lam, total_size, dx):
        super(freespace_layer, self).__init__()
        f_kernel = gen_f_kernel(prop, lam, total_size, dx)
        self.register_buffer('fk_const', f_kernel)
    def forward(self, En):
        Ef = fourier_conv1D(En, self.fk_const)
        return Ef
    
def propagator(prop, lam, total_size, dx):
    '''
        prop distance in free space
    '''
    def W(x, y, z, wavelength):
        r = np.sqrt(x*x+y*y+z*z)
        #w = z/r**2*(1/(np.pi*2*r)+1/(relative_wavelength*1j))*np.exp(1j*2*np.pi*r/relative_wavelength)
        w = z/(r**2)*(1/(wavelength*1j))*np.exp(1j*2*np.pi*r/wavelength)
        return w
    #plane_size: the numerical size of plane, this is got by (physical object size)/(grid)

    x = np.arange(-(total_size-1), total_size,1) * dx
    G = W(x, 0, prop, lam)
    return G

def gen_f_kernel(prop, lam, total_size, dx):
    G = propagator(prop, lam, total_size, dx)
    f_kernel = np.fft.fft(np.fft.ifftshift(G))
    f_kernel = torch.tensor(f_kernel, dtype = torch.complex64)
    print("f_kernel generated.")
    return f_kernel

class Ideal_model(nn.Module):
    def __init__(self, prop_dis, GP, total_size):
        super(Ideal_model, self).__init__()
        self.prop = prop_dis
        self.phase = torch.nn.Parameter(torch.empty((total_size,), dtype = torch.float))
        self.freelayer1 = freespace_layer(self.prop, GP.lam, total_size, GP.dx)
    def forward(self, E0):
        E = E0 * torch.exp(1j * self.phase)
        Ef = self.freelayer1(E)
        If = torch.abs(Ef)**2
        return If