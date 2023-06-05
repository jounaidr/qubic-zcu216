from matplotlib import pyplot
import numpy
from qubic.qcvv.crfullxy import c_crfullxy

qubitid=['Q1','Q2']
qubitid=['Q0','Q1']
qubitid=['Q3','Q2']
crfullxy=c_crfullxy(qubitid=qubitid,calirepo='submodules/qchip')#,debug=3)
xyrot=numpy.linspace(0,2*numpy.pi,100)
zprepdeg=numpy.array([[246,147],[314,234],[336,37]])
zprep=zprepdeg*numpy.pi/180.0
crfullxy.seqs(zprep=zprep,xyrot=xyrot)
crfullxy.run(400,combineorder=qubitid)
crfullxy.plot()

updatedict=crfullxy.optimize()
print(updatedict)
crfullxy.opts['qchip'].updatecfg(updatedict)#,'cali/qubitcfg_X6Y3.json')

from qubic.qcvv.cnot import c_cnot
cnot=c_cnot(qubitid=qubitid,calirepo='submodules/qchip')
cnot.runseqs(nsample=200)
for k,v in sorted(cnot.result.items()):
	print(k,''.join(['%8.3f'%i for i in  v]))
pyplot.show()
