from matplotlib import pyplot
import sys
from qubic.qcvv.repeatgate import c_repeatgate
qubitid=sys.argv[1]
repeatgate=c_repeatgate(qubitid=qubitid,calirepo='submodules/qchip',debug=2,plot=True)
repeatgate.optimizesetup(gate='X90',initspan=0.1,ngatemult=4,ngateadd=2)
updatedict=repeatgate.optimize(nsample=10,nsteps=9)
print(updatedict)
#repeatgate.opts['qchip'].updatecfg(updatedict,'cali/qubitcfg_X6Y3.json')
sys.stdout.flush()
pyplot.ioff()
pyplot.show()

