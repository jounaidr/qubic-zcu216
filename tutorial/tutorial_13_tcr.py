from matplotlib import pyplot
import numpy
from qubic.qcvv.tcr import c_tcr

qubitid=['Q1','Q2']
qubitid=['Q0','Q1']
qubitid=['Q3','Q2']
tcr=c_tcr(qubitid=qubitid,calirepo='submodules/qchip',debug=3)
tcrlist=numpy.arange(80e-9,640e-9,8e-9)

tcr.seqs(tcrlist=tcrlist,repeat=1,amp=0.5)
tcr.run(50,combineorder=qubitid)
result=tcr.fit()
tcr.plot(plotfit=True)
pyplot.show()

#tcrsel=288e-9
#updatedict=tcr.optimize(nsample=100,tcr=tcrsel,plot=True,nsteps=3)#,acenter=0.2,aspan=0.1)
#print(updatedict)
