from matplotlib import pyplot
import trueq
circuits = trueq.make_srb(labels=[(0,1)], n_random_cycles=[2,8,16], n_circuits=20,twirl='U')

from qubic.trueqqubic.trueqqubic import c_trueqqubic
tq = c_trueqqubic(qubitid=['Q1','Q0'], calirepo='submodules/qchip')
tq.seqs(circuits)
result = tq.run(400)
print(result)
tq.plot()
pyplot.show()
for cs in tq.opts['seqs']:
	for l in cs:
		print(l)

