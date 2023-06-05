from matplotlib import pyplot
import sys
from qubic.qcvv.spinecho import c_spinecho


spinecho=c_spinecho(qubitid=sys.argv[1],calirepo='submodules/qchip')
spinecho.seqs(elementstep=4e-6,elementlength=40)
spinecho.run(200)
spinecho.fit()
print(spinecho.result)
fig1=pyplot.figure(figsize=(15,15))
sub=fig1.subplots(1,1)
spinecho.plot(fig=sub)
spinecho.plottyfit(fig=sub)
pyplot.show()

