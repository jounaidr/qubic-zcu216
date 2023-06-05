from matplotlib import pyplot
import sys
from qubic.qcvv.chevron import c_chevron

qubitid=sys.argv[1]
chevron=c_chevron(qubitid=qubitid,calirepo='submodules/qchip')

freq=chevron.opts['qchip'].getfreq(qubitid+'.freq')
fbw=100e6
chevron.seqs(fstart=freq-fbw/2,fstop=freq+fbw/2,elementlength=41,elementstep=8e-9,fsteps=10,overlapcheck=False)
chevron.run(20)
chevron.fit()

fig1=pyplot.figure(figsize=((30,10)))
ax1=fig1.subplots(2,1)
chevron.plot(ax1[:])

fig2=pyplot.figure(figsize=(15,8))
ax2=fig2.subplots()
chevron.iqplot(ax2)
chevron.gmmplot(ax2)
fig3=pyplot.figure('ampfit')
ax3=fig3.subplots()
chevron.ampfitplot(ax3)
fig4=pyplot.figure('rsqr')
ax4=fig4.subplots()
chevron.rsqrplot(ax4)
pyplot.show()
