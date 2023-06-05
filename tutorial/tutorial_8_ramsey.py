from matplotlib import pyplot
import sys
from qubic.qcvv.ramsey import c_ramsey

ramsey=c_ramsey(qubitid=sys.argv[1],calirepo='submodules/qchip')
if 1:
	ramsey.seqs(framseydelta=00e3,elementstep=1e-6,elementlength=80,logx=False)
	ramsey.run(400)
	print(ramsey.fit())
else:
	updatedict=ramsey.optimize(20,elementstep=1.4e-6,elementlength=80,logx=False,plot=True)
	ramsey.opts['qchip'].updatecfg(updatedict,'submodules/qchip/chip57/qubitcfg_chip57.json')
	print(updatedict)
fig1=pyplot.figure(figsize=(15,15))
sub=fig1.subplots(1,1)
ramsey.plot(fig=sub)
ramsey.plottyfit(fig=sub)
pyplot.show()

