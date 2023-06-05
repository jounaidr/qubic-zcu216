from matplotlib import pyplot
import sys
from qubic.qcvv.rabioptimize import c_rabioptimize
qubitid=sys.argv[1]
calirepo='submodules/qchip'
rabioptimize=c_rabioptimize(qubitid=qubitid,calirepo=calirepo,debug=3,gmixs=None,plot=False)
print(rabioptimize.optimize(nsample=50,disp=3))
pyplot.ioff()
pyplot.show()
