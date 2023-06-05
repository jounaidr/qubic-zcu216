from matplotlib import pyplot
import numpy
import sys
from qubic.qcvv.dragalpha import c_dragalpha
qubitid=sys.argv[1]
dragalpha=c_dragalpha(qubitid=qubitid,calirepo='submodules/qchip')
if 1:
	dragalpha.seqs(alphas=numpy.arange(-3,3,0.1))
	dragalpha.run(100)
	print(dragalpha.fit())
else:
	updatedict=dragalpha.optimize(500)#,alphas=numpy.arange(-5,5,0.2)))
	print(updatedict)
	dragalpha.opts['qchip'].updatecfg(updatedict,'cali/qubitcfg_X6Y3.json')
fig1=pyplot.figure(figsize=(15,15))
sub=fig1.subplots(1,1)
dragalpha.plot(fig=sub)
pyplot.show()

