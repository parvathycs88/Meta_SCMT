import numpy as np
import matplotlib

paper_colors = [1.00000,1.00000,1.00000,0.97745,0.98595,0.99641,0.95490,0.97190,0.99281,0.93235,0.95784,0.98922,0.90980,0.94379,0.98562,0.88725,0.92974,0.98203,0.86471,0.91569,0.97843,0.84216,0.90163,0.97484,0.81961,0.88758,0.97124,0.79706,0.87353,0.96765,0.77451,0.85948,0.96405,0.75196,0.84542,0.96046,0.72941,0.83137,0.95686,0.70407,0.84434,0.91403,0.67873,0.85732,0.87119,0.65339,0.87029,0.82836,0.62805,0.88326,0.78552,0.60271,0.89623,0.74268,0.57738,0.90920,0.69985,0.55204,0.92217,0.65701,0.52670,0.93514,0.61418,0.50136,0.94811,0.57134,0.47602,0.96109,0.52851,0.45068,0.97406,0.48567,0.42534,0.98703,0.44284,0.40000,1.00000,0.40000,0.44615,1.00000,0.36923,0.49231,1.00000,0.33846,0.53846,1.00000,0.30769,0.58462,1.00000,0.27692,0.63077,1.00000,0.24615,0.67692,1.00000,0.21538,0.72308,1.00000,0.18462,0.76923,1.00000,0.15385,0.81538,1.00000,0.12308,0.86154,1.00000,0.09231,0.90769,1.00000,0.06154,0.95385,1.00000,0.03077,1.00000,1.00000,0.00000,1.00000,0.92308,0.00000,1.00000,0.84615,0.00000,1.00000,0.76923,0.00000,1.00000,0.69231,0.00000,1.00000,0.61538,0.00000,1.00000,0.53846,0.00000,1.00000,0.46154,0.00000,1.00000,0.38462,0.00000,1.00000,0.30769,0.00000,1.00000,0.23077,0.00000,1.00000,0.15385,0.00000,1.00000,0.07692,0.00000,1.00000,0.00000,0.00000,0.96667,0.01667,0.00000,0.93333,0.03333,0.00000,0.90000,0.05000,0.00000,0.86667,0.06667,0.00000,0.83333,0.08333,0.00000,0.80000,0.10000,0.00000,0.76667,0.11667,0.00000,0.73333,0.13333,0.00000,0.70000,0.15000,0.00000,0.66667,0.16667,0.00000,0.63333,0.18333,0.00000,0.60000,0.20000,0.00000]
paper_colors = np.array(paper_colors)
paper_colors = paper_colors.reshape(-1,3)
paper_cmap = matplotlib.colors.ListedColormap(paper_colors)