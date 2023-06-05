from matplotlib import pyplot
import sys
from qubic.qcvv.t1 import c_t1

t1=c_t1(qubitid=sys.argv[1],calirepo='submodules/qchip')
t1.seqs()
t1.run(50)
t1.fit()
print(list(t1.accresult.keys()))
print(t1.result)

fig1=pyplot.figure(figsize=(15,15))
sub=fig1.subplots(2,2)
t1.plot(fig=sub[0,0])
t1.iqplot(sub[0,1])
#t1.iqplotafterheralding(sub[1,1])
pyplot.show()
