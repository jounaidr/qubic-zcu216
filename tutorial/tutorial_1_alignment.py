from matplotlib import pyplot
from qubic.qcvv.alignment import c_alignment


alignment=c_alignment(qubitid='alignment',calirepo='submodules/qchip',debug=False,sim=True)
tlo=692e-9
alignment.seqs(tlo=tlo,mon_sel0=0,mon_sel1=3)
alignment.run(1000)
fig1=pyplot.figure(1,figsize=(15,8))
alignment.plot(fig1)
pyplot.show()
