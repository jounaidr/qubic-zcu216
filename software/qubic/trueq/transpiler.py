import matplotlib.pyplot as plt
import trueq as tq
import numpy as np

def transpile(trueq_circuit, label_to_qubit, entangler='cz', delay_before_circuit=400.e-6):
    """
    Parameters
    ----------
        trueq_circuit : trueq.circuits.Circuit or CircuitCollection
        label_to_qubit : dict or list
            if dict, keys are trueq labels (ints) and values are qubitids ('Q0', 'Q1', etc)
            if list of qubitids, label 0 is assumed to be the first element, etc
        entangler : str
            either 'cz' or 'cnot'
        delay_before_circuit : float
            delay (in seconds) for qubit relaxation
    """
    if isinstance(trueq_circuit, tq.circuits.Circuit):
        return _transpile(trueq_circuit, label_to_qubit, entangler, delay_before_circuit)
    elif isinstance(trueq_circuit, tq.circuits.CircuitCollection):
        qubic_circuits = []
        for circuit in trueq_circuit:
            qubic_circuits.append(_transpile(circuit, label_to_qubit, entangler, delay_before_circuit))
        return qubic_circuits
    else:
        raise TypeError

def _transpile(trueq_circuit, label_to_qubit, entangler='cz', delay_before_circuit=400.e-6):
    """
    Parameters
    ----------
        trueq_circuit : trueq.circuits.Circuit
        label_to_qubit : dict or list
            if dict, keys are trueq labels (ints) and values are qubitids ('Q0', 'Q1', etc)
            if list of qubitids, label 0 is assumed to be the first element, etc
        entangler : str
            either 'cz' or 'cnot'
        delay_before_circuit : float
            delay (in seconds) for qubit relaxation
    """
    if entangler.lower() == 'cz':
        entangler = tq.Gate.cz
    elif entangler.lower() == 'cnot':
        entangler = tq.Gate.cnot
    else:
        raise Exception('{} entangler not supported'.format(entangler))
    compiler = tq.Compiler.basic(entangler, mode='ZXZXZ')
    compiled_circuit = compiler.compile(trueq_circuit)

    qubic_circuit = [{'name': 'delay', 't': delay_before_circuit}]

    for cycle in compiled_circuit:
        qubic_circuit.append({'name': 'barrier'})
        for labels, operation in cycle:
            qubits = [label_to_qubit[l] for l in labels]
            if isinstance(operation, tq.operations.Meas):
                assert(len(labels) == 1)
                qubic_circuit.append({'name': 'read', 'qubit': qubits})
            elif operation.name == 'sx':
                assert len(labels) == 1
                assert operation.parameters == {}
                qubic_circuit.append({'name': 'X90', 'qubit': qubits})
            elif operation.name == 'z':
                assert len(labels) == 1
                qubic_circuit.append({'name': 'virtualz', 'qubit': qubits,
                                      'phase': np.deg2rad(operation.parameters['phi'])})
            elif operation.name == 'cz':
                qubic_circuit.append({'name': 'CZ', 'qubit': qubits})
            elif operation.name == 'cnot' or operation.name == 'cx':
                qubic_circuit.append({'name': 'CNOT', 'qubit': qubits})

            else:
                raise Exception('{} not supported'.format(operation))

    return qubic_circuit

