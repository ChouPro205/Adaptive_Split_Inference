import sys
import torch
import numpy as np
import pandas as pd
import scipy
import matplotlib
import wfdb
import sklearn

print("Python       :", sys.version.split()[0])
print("Executable   :", sys.executable)
print("PyTorch      :", torch.__version__)
print("NumPy        :", np.__version__)
print("Pandas       :", pd.__version__)
print("SciPy        :", scipy.__version__)
print("Matplotlib   :", matplotlib.__version__)
print("WFDB         :", wfdb.__version__)
print("Scikit-learn :", sklearn.__version__)

print("\nCUDA available:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))

x = torch.tensor([1.0, 2.0, 3.0])
print("\nPyTorch sanity:", x * 2)

print("\nENVIRONMENT OK")