import qubic.job_manager as jm
import numpy as np
import trueq as tq
import qubic.trueq.transpiler as tp
import copy

class TrueQJobManager:

    def __init__(self, fpga_config, qchip, channel_configs, circuit_runner, 
                 gmm_manager=None, target_platform='rfsoc'):
        self.job_manager = jm.JobManager(fpga_config, qchip, channel_configs,
                                         circuit_runner, gmm_manager, target_platform)

    def build_and_run_circuits(self, trueq_circuits, label_to_qubit, n_total_shots, entangler='cz',
            outputs=['trueq_results'], fit_gmm=False, reads_per_shot=1, delay_per_shot=500.e-6, qchip=None):

        qubic_outputs = copy.copy(outputs)
        if 'trueq_results' in outputs:
            qubic_outputs.remove('trueq_results')
            qubic_outputs.append('counts')

        qubic_circuits = tp.transpile(trueq_circuits, label_to_qubit, entangler, 400.e-6)
        if isinstance(qubic_circuits[0], dict):
            qubic_circuits = [qubic_circuits]

        qubic_output_dict = self.job_manager.build_and_run_circuits(qubic_circuits, n_total_shots, qubic_outputs, fit_gmm=fit_gmm,
                                                                    reads_per_shot=reads_per_shot, delay_per_shot=delay_per_shot, qchip=qchip)

        output_dict = {}
        for output_type in outputs:
            if output_type == 'trueq_results':
                output_dict['trueq_results'] = batchcounts_to_results(qubic_output_dict['counts'], label_to_qubit)
            else:
                output_dict[output_type] = qubic_output_dict[output_type]

        return output_dict



    def collect_trueq_results(self, circuit_list, n_total_shots):
        pass


def batchcounts_to_results(batchcounts, label_to_qubit):
    """
    Parameters
    ----------
        batchcounts : qubic BatchCounts object
        label_to_qubit : list or dict
            mapping from trueq labels (indices) to physical qubits
    """
    tq_results = []
    if isinstance(label_to_qubit, dict):
        qubit_to_label = {qubit: label for label, qubit in label_to_qubit.items()}
    elif isinstance(label_to_qubit, list) or isinstance(label_to_qubit, np.ndarray):
        qubit_to_label = {qubit: label for label, qubit in enumerate(label_to_qubit)}
    if list(batchcounts.bitstring_dict.values())[0].shape[1] != 1:
        raise Exception('Multiple reads per shot not supported!')

    n_circuits = list(batchcounts.bitstring_dict.values())[0].shape[0]

    qubic_to_tq_bitstring = {}
    for tq_bitstring in batchcounts.bitstring_dict.keys():
        #enumerate all bitstrings as tq strings, then backsolve for qubic mapping
        qb_bitstring = ''.join([tq_bitstring[qubit_to_label[batchcounts.qubits[i]]] for i in range(len(tq_bitstring))])
        qubic_to_tq_bitstring[qb_bitstring] = tq_bitstring

    for circ_ind in range(n_circuits):
        result_dict = {qubic_to_tq_bitstring[bitstring]: counts[circ_ind] for 
                       bitstring, counts in batchcounts.bitstring_dict.items()}
        tq_results.append(tq.Results(result_dict))

    return tq_results


