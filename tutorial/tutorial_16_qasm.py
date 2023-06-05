qasm0='''OPENQASM 3.0;
qreg q[2];
creg meas[2];
measure q[0] -> meas[0];
measure q[1] -> meas[1];
'''
qasm1='''OPENQASM 3.0;
qreg q[2];
creg meas[2];
sx q[0];
sx q[1];
barrier q;
measure q[0] -> meas[0];
measure q[1] -> meas[1];
'''
qasm2='''OPENQASM 3.0;
qreg q[2];
creg meas[2];
sx q[0];
sx q[0];
sx q[1];
sx q[1];
barrier q;
measure q[0] -> meas[0];
measure q[1] -> meas[1];
'''

import sys
qasms=[qasm0,qasm1,qasm2]
from qubic.qasmqubic.qasmrun import qasmrun
qasmresult=qasmrun(nsample=200,qasms=qasms,qubitsmap={'q':['Q1','Q3']},heraldingqasm=[qasm0])
print(qasmresult['countsum']['vsingle'])
