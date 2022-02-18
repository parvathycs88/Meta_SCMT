from importlib.resources import path
from statistics import mode
import numpy as np
import matplotlib.pyplot as plt
import torch
from sklearn.preprocessing import PolynomialFeatures
from .utils import gen_decay_rate

class LinearModel(torch.nn.Module):
    def __init__(self, modes, order):
        super(LinearModel, self).__init__()
        self.order = order
        self.fc = torch.nn.Linear(self.order, modes)
    def forward(self, poly_h):
        return self.fc(poly_h)

class Model(torch.nn.Module):
    def __init__(self, modes, layers = 2, nodes = 64):
        super(Model, self).__init__()
        module_list = [torch.nn.Linear(1, nodes), torch.nn.ReLU()]
        for _ in range(layers):
            module_list.append(torch.nn.Linear(nodes, nodes))
            module_list.append(torch.nn.ReLU())
        module_list.append(torch.nn.Linear(nodes, modes))
        self.fc = torch.nn.Sequential(*module_list)
    def forward(self, x):
        return self.fc(x)
           
class Fitting_neffs():
    def __init__(self, modes, gen_modes, dh, path) -> None:
        self.gen_modes = gen_modes
        self.model = None
        self.modes = modes
        self.dh = dh
        self.path = path
        
    def fit(self, layers = 2, steps = 10000, lr = 0.001, vis = True):
        if torch.cuda.is_available():
            device = 'cuda'
        else:
            device = 'cpu'
        log_steps = int(steps // 10)
        self.model = Model(self.modes, layers)
        self.model = self.model.to(device)
        modes_lib = self.gen_modes.modes_lib
        if modes_lib == None:
            raise Exception("gen modes first!")
        widths, neffs= gen_fitting_data(self.modes, modes_lib, self.dh)
        X = torch.tensor(widths, dtype = torch.float, device= device)
        Y = torch.tensor(neffs, dtype = torch.float, device= device)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        decay_rate = gen_decay_rate(steps, log_steps)
        my_lr_scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, gamma=decay_rate)
        mse = torch.nn.MSELoss(reduction = 'sum')
        for step in range(steps):
            Y_pred = self.model(X)
            loss = mse(Y_pred, Y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            if step % log_steps == 0:
                if step != 0:
                    my_lr_scheduler.step()
                relative_error = torch.mean(torch.abs(Y_pred - Y)/torch.abs(Y)) * 100
                relative_error = relative_error.cpu().detach().numpy()
                print("relative_error:" + str(relative_error) + "%.")
                if relative_error < 0.1:
                    print("fitting error < 0.1%, accurate enough, stoped.")
                    torch.save(self.model, self.path + "fitting_neffs_state_dict")
                    print("model saved.")
                    break
        if relative_error > 0.1:
            print("fitting error > 0.1%, increase total steps or number of layers in fullconnected network.")
        if vis:
            plt.figure()
            pred_neffs = Y_pred.cpu().detach().numpy()
            for mode in range(self.modes):
                mode_neffs = neffs[:, mode]
                pred_mode_neffs = pred_neffs[:, mode]
                plt.plot(widths, mode_neffs, label = "mode:" + str(mode))
                plt.plot(widths, pred_mode_neffs, linestyle = '--', label = "mode:" + str(mode))
                plt.legend()
            plt.xlabel("widths [um]")
            plt.ylabel("neffs")
            plt.show()

    def apply(self, X):
        '''
            input: waveguides widths, type: numpy.
            output: neffs for each waveguides and modes. column 0 store mode 0, col 1 store mode 1 ...
        '''
        if self.model == None:
            print("fit the model first!")
        else:
            self.model = self.model.to('cpu')
            X = np.array(X)
            X = X.reshape(X.size, 1)
            X = torch.tensor(X, dtype= torch.float)
            with torch.no_grad():
                Y = self.model(X)
                Y = Y.numpy()
            return Y
        
    def polyfit(self,order, steps = 10000, lr = 0.01, vis = True):
        if torch.cuda.is_available():
            device = 'cuda'
        else:
            device = 'cpu'
        log_steps = int(steps // 10)
        self.model = LinearModel(self.modes, order)
        self.model = self.model.to(device)
        modes_lib = self.gen_modes.modes_lib
        if modes_lib == None:
            raise Exception("gen modes first!")
        widths, neffs, X, Y = gen_polyfitting_data(self.modes, modes_lib, order, self.dh)
        X = torch.tensor(X, dtype = torch.float, device= device)
        Y = torch.tensor(Y, dtype = torch.float, device= device)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        mse = torch.nn.MSELoss(reduction = 'sum')
        for step in range(steps):
            Y_pred = self.model(X)
            loss = mse(Y_pred, Y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            if step % log_steps == 0:
                relative_error = torch.mean(torch.abs(Y_pred - Y)/torch.abs(Y)) * 100
                relative_error = relative_error.cpu().detach().numpy()
                print("relative_error:" + str(relative_error) + "%.")
        if relative_error < 0.1:
            print("fitting error < 0.1%, successed.")
        else:
            print("fitting error > 0.1%, increase total steps or polynomial fitting order.")
        if vis:
            plt.figure()
            pred_neffs = Y_pred.cpu().detach().numpy()
            for mode in range(self.modes):
                mode_neffs = neffs[:, mode]
                pred_mode_neffs = pred_neffs[:, mode]
                plt.plot(widths, mode_neffs, label = "mode:" + str(mode))
                plt.plot(widths, pred_mode_neffs, linestyle = '--', label = "mode:" + str(mode))
                plt.legend()
            plt.xlabel("widths [um]")
            plt.ylabel("neffs")
            plt.show()

def gen_fitting_data(modes, modes_lib, dh):
    X = []
    Y = []
    for key in modes_lib.keys():
        h = key * dh
        X.append(h)
        y = []
        for m in range(modes):
            y.append(modes_lib[key][m]['neff'])
        Y.append(y)
    X = np.array(X)
    Y = np.array(Y)
    X = X.reshape((X.shape[0], 1))
    widths = X
    neffs = Y
    return widths, neffs
     
def gen_polyfitting_data(modes, modes_lib, order, dh):
    X = []
    Y = []
    for key in modes_lib.keys():
        h = key * dh
        X.append(h)
        y = []
        for m in range(modes):
            y.append(modes_lib[key][m]['neff'])
        Y.append(y)
    X = np.array(X)
    Y = np.array(Y)
    widths = X
    neffs = Y
    poly = PolynomialFeatures(order, include_bias=False)
    X = X.reshape((X.shape[0], 1))
    X = poly.fit_transform(X)
    return widths, neffs, X, Y

    
        