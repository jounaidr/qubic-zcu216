pygsti_to_qubic = {
        'Gxpi2': 'X90',
        'Gcr': 'CR',
        'Gzpi2': 'Z90',
        'Gxx': ['X90', 'X90'],
        'Gxy': ['X90', 'Y90'],
        'Gyx': ['Y90', 'X90']}


def parse_pygsti_circuit(circuit, qubit_map):
    qubic_circuit = []
    for layer in circuit:
        qubic_circuit.extend(parse_layer(layer, qubit_map))
        qubic_circuit.append({'name': 'barrier', 'qubit': qubit_map})

    return qubic_circuit


def parse_layer(layertup, qubit_map):
    layercirc = []
    if layertup.name == 'COMPOUND':
        for layer in layertup:
            layercirc.extend(parse_layer(layer, qubit_map))
    else:
        if isinstance(pygsti_to_qubic[layertup.name], str):
            layercirc = [{'name': pygsti_to_qubic[layertup.name],
                    'qubit': [qubit_map[n] for n in layertup.qubits]}]
        else:
            layercirc = []
            for i, gatename in enumerate(pygsti_to_qubic[layertup.name]):
                layercirc.append({'name': gatename, 'qubit': [qubit_map[layertup.qubits[i]]]})

    return layercirc
