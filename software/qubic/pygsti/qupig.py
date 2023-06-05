import pygsti

pygsti_to_qubic = {
        'Gxpi2': 'X90',
        'Gcr': 'CR',
        'Gzpi2': 'Z90',
        'Gxx': ['X90', 'X90'],
        'Gxy': ['X90', 'Y90'],
        'Gyx': ['Y90', 'X90']}


def parse_layer(layertup):
        layercirc = []
        if layertup.name == 'COMPOUND':
                for layer in layertup:
                        layercirc.extend(parse_layer(layer))
        else:
                if isinstance(pygsti_to_qubic[layertup.name], str):
                        layercirc = [{'name': pygsti_to_qubic[layertup.name],
                                      'qubit': list(layertup.qubits)}]
                else:
                        layercirc = []
                        for i, gatename in enumerate(pygsti_to_qubic[layertup.name]):
                                layercirc.append({'name': gatename,
                                                  'qubit': list(layertup.qubits)})
        return layercirc

def qubic_instructions_from_pygsti_circuit(pygsti_circuit, readout_register):
    qubic_circuit = list()
    qubic_circuit.append({'name': 'delay', 't': 400.e-6})
    for layer in pygsti_circuit:
        qubic_circuit.extend(parse_layer(layer))
        qubic_circuit.append({'name': 'barrier', 'qubit': list(readout_register)})
    for qid in readout_register:
        qubic_circuit.append({'name': 'read', 'qubit': [qid]}, )
    return qubic_circuit

# class PyGSTiCircuitMaker:
#     def __init__(self, pspec: QubitProcessorSpec):
#         self.spec = pspec
#         self.target_model = pygsti.models.modelconstruction.create_explicit_model(pspec)
#
#     def update(self, keys_or_dict, value=None):
#         self.qchip.update(keys_or_dict, value)

def shots_to_pygsti_dataset(shot_dictionary, pspec):
    return -1

