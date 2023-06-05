from matplotlib import pyplot
import numpy
import sys
from qubic.qcvv.rabi import c_rabi
rabi=c_rabi(qubitid=sys.argv[1],calirepo='submodules/qchip',gmixs=None)
rabi.seqs_w(elementlength=80,elementstep=4e-9)
rabi.run(500)
rabi.fit()
if rabi.opts['gmixs'] is None:
	rabi.savegmm()
else:
	print(rabi.opts['gmixs'])

fig,(sub1,sub2)=pyplot.subplots(2,1)
fig.suptitle(sys.argv[1])
rabi.psingleplot(sub1)
rabi.iqplot(sub2)
rabi.gmmplot(sub2)
pyplot.show()
