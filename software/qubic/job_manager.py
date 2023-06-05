import abc
from abc import ABC
from collections import OrderedDict
import qubic.state_disc as sd
import pygsti.processors
import qubic.toolchain as tc
from distproc.compiler import CompiledProgram
from collections import OrderedDict
import numpy as np
import qubic.toolchain as tc

import itertools
try:
    import ipdb
except ImportError:
    pass
from collections import OrderedDict

class JobManager:
    """
    TODO: add readout correction and heralding
    """

    def __init__(self, fpga_config, channel_configs, circuit_runner, qchip,
                 gmm_manager=None, target_platform='rfsoc'):
        self.fpga_config = fpga_config
        self.channel_configs = channel_configs
        self.runner = circuit_runner
        self.qchip = qchip

        if gmm_manager is None: # instantiate empty GMMManager
            self.gmm_manager = sd.GMMManager(chanmap_or_chan_cfgs=channel_configs)
        elif isinstance(gmm_manager, str):
            self.gmm_manager = sd.GMMManager(load_file=gmm_manager, chanmap_or_chan_cfgs=channel_configs)
        else:
            assert isinstance(gmm_manager, sd.GMMManager)
            self.gmm_manager = gmm_manager

    def build_and_run_circuits(self, program_list, n_total_shots, outputs=['s11'],
            fit_gmm=False, reads_per_shot=1, delay_per_shot=500.e-6, qchip=None):
        """
        Parameters
        ----------
            outputs : list
                list of 's11', 'shots', and/or 'counts'

        TODO: get rid of stuff that uses fit_gmm then remove this option
        """
        if qchip is None:
            qchip = self.qchip

        if not isinstance(program_list, list):
            raise TypeError("program_list of invalid type")

        if isinstance(program_list[0], list):
            if 'name' in program_list[0][0]: #this is a gate level program
                self.compiled_progs = tc.run_compile_stage(program_list, self.fpga_config, qchip)
                self.raw_asm_progs = tc.run_assemble_stage(self.compiled_progs, self.channel_configs)
            else:
                raise TypeError('{} invalid program list'.format(program_list))

        elif isinstance(program_list[0], dict): #this is raw asm
            #todo: put in check for raw asm
            self.raw_asm_progs = program_list

        elif isinstance(program_list[0], CompiledProgram):
            self.compiled_progs = program_list
            self.raw_asm_progs = tc.run_assemble_stage(self.compiled_progs, self.channel_configs)

        else:
            raise TypeError('{} invalid program list'.format(program_list))

        s11 = self.runner.run_circuit_batch(self.raw_asm_progs, n_total_shots, reads_per_shot, delay_per_shot)

        output_dict = {}

        if fit_gmm:
            self.gmm_manager.fit(s11)

        if 's11' in outputs:
            output_dict['s11'] = s11
        if 'shots' in outputs or 'counts' in outputs:
            shots = self.gmm_manager.predict(s11)
            if 'shots' in outputs:
                output_dict['shots'] = shots
            if 'counts' in outputs:
                output_dict['counts'] = BatchCounts(shots)


        return output_dict

    def collect_raw_IQ(self, program_list, num_shots_per_circuit,
                             reads_per_shot=1, delay_per_shot=500.e-6, qchip=None):
        output_dict = self.build_and_run_circuits(program_list, num_shots_per_circuit, ['s11'],
                                                    reads_per_shot=reads_per_shot, delay_per_shot=delay_per_shot, qchip=qchip)
        return output_dict['s11']

    def collect_classified_shots(self, program_list, num_shots_per_circuit, 
                             reads_per_shot=1, delay_per_shot=500.e-6, qchip=None):
        output_dict = self.build_and_run_circuits(program_list, num_shots_per_circuit, ['shots'],
                                                    reads_per_shot=reads_per_shot, delay_per_shot=delay_per_shot, qchip=qchip)
        return output_dict['shots']

    def collect_counts(self, qubic_instruction_list_or_dict, num_shots_per_circuit,
                             reads_per_shot=1, delay_per_shot=500.e-6, qchip=None):
        output_dict = self.build_and_run_circuits(program_list, num_shots_per_circuit, ['counts'],
                                                    reads_per_shot=reads_per_shot, delay_per_shot=delay_per_shot, qchip=qchip)
        return output_dict['counts']

class PyGSTiJobManager(JobManager):
    def __init__(self, fpga_config, channel_configs, circuit_runner, qchip,
                 gmm_manager, target_platform='rfsoc'):
        if gmm_manager is None:
            raise(ValueError("PyGSTiJobManager needs a gmm_manager!"))
        super().__init__(fpga_config, channel_configs, circuit_runner, qchip,
                 gmm_manager, target_platform)

    def collect_dataset(self, job_dict, num_shots_per_circuit, qchip):
        if not isinstance(job_dict, (dict, OrderedDict)):
            raise(ValueError("the jobs should be a dictionary"))
        shots = self.collect_classified_shots(list(job_dict.values()), num_shots_per_circuit, qchip=qchip)


        ds = pygsti.data.DataSet(outcome_labels=[bin(i)[2:].zfill(3) for i in range(2**3)])
        for id_circ, circ in enumerate(job_dict.keys()):
            counts = dict()
            for id_shot in range(num_shots_per_circuit):
                bits = ''
                for qid in shots.keys():
                    bits += str(shots[qid][id_circ][id_shot][0])
                if bits in counts:
                    counts[bits] += 1
                else:
                    counts[bits] = 1
            ds[circ] = counts
        return ds
                
class BatchCounts:
    """
    Object for storing shot count results (i.e. number of '000', '100', etc) from a batch of 
    experiments. 

    Counts are summed along the nshots dimension, so bitstring count values have shape 
    (n_circuits, reads_per_shot)

    Attributes:
        count_dict: dictionary of counts indexed by bitstring formatted as tuple of sequential gmm labels
        bitstring_dict: dictionary of counts indexed by bitstring literal

    TODO:
        add heralded bitstring dict
    """

    def __init__(self, shot_dict, gmm_labels=[0, 1]):
        self.qubits = sorted(shot_dict.keys())
        self.shot_dict = OrderedDict()
        for qubit in self.qubits:
            self.shot_dict[qubit] = shot_dict[qubit]

        self.bit_tuples = [bittuple for bittuple in itertools.product(*[gmm_labels for i in range(len(self.qubits))])]

        self._generate_counts()

        self._bitstring_dict = None

    def _generate_counts(self):
        count_dict = {}
        shot_array = np.array([shots for shots in self.shot_dict.values()]) #this should have dims (nqubits, n_circuts, nshots, reads_per_shot)
        for bit_tuple in self.bit_tuples:
            #shape (n_circuits, nshots, reads_per_shot); i.e. does this measurement satisfy the current bit tuple?
            bitstring_sat_mask = np.asarray([c for c in (shot_array[i] == bit_tuple[i] for i in range(len(self.qubits)))])
            bitstring_sat = np.prod(bitstring_sat_mask, axis=0) 
            count_dict[bit_tuple] = np.sum(bitstring_sat, axis=1) #sum over nshots, shape is (n_circuits, reads_per_shot)

        self.count_dict = count_dict

    @property 
    def bitstring_dict(self):
        """
        lazy generation + store
        """
        if self._bitstring_dict is None:
            self._bitstring_dict = {}
            for bit_tuple in self.bit_tuples:
                bitstring = ''.join([str(bit) for bit in bit_tuple])
                self._bitstring_dict[bitstring] = self.count_dict[bit_tuple]

        return self._bitstring_dict


class SimulationManager:
    def __init__(self, pygsti_model, seed=None, simulation_type='multinomial', readout_register=None):
        self.model = pygsti_model
        self.seed = seed
        self.simulation_type = simulation_type
        self.readout_register = readout_register

    def collect_classified_shots(self, job_dict, num_shots_per_circuit,
                       reads_per_shot=1, delay_per_shot=500.e-6):
        """
        Mimics the qubic collect classified shots, simulates the outcomes and arranges into
        a dictionary of datastreams with keys that are the readout qubits

        must unpack the pygsti dataset and convert it into qubic form,
        there is freedom in the ordering of the data, I'll just stack bitstrings in an arbitrary order
        """

        if self.simulation_type == 'multinomial':
            assert type(job_dict) is OrderedDict
            ds = pygsti.data.simulate_data(self.model, list(job_dict.keys()), num_shots_per_circuit,
                                       seed=self.seed)
            num_outcomes = len(ds.outcome_labels)
            output_stream = {
                qid: np.zeros((len(job_dict), num_shots_per_circuit, 1)) for qid in self.readout_register
            }
            for id_circ, circ in enumerate(job_dict.keys()):
                counts = ds[circ].counts
                iterator_counts = 0  # used to iterate over all the counts
                for bitstring in counts.keys():
                    for id_bit, bit in enumerate(bitstring[0]):
                        if bit == '1':
                            assert (counts[bitstring] - int(counts[bitstring])) < 1e-12
                            for i in range(iterator_counts, iterator_counts + int(counts[bitstring])):
                                output_stream[self.readout_register[id_bit]][id_circ, i, 0] = 1
                    iterator_counts += int(counts[bitstring])
            return output_stream



        elif self.simulation_type == 'scaled_probability':
            # TODO: implement scaled probability simulation type
            pass

    def collect_dataset(self, job_dict, num_shots_per_circuit, qchip):
        """
                Mimics the qubic collect classified shots, simulates the outcomes and arranges into
                a dictionary of datastreams
                """
        if self.simulation_type == 'multinomial':
            ds = pygsti.data.simulate_data(self.model, list(job_dict.keys()), num_shots_per_circuit,
                                           seed=self.seed)
            return ds
        elif self.simulation_type == 'scaled_probability':
            pass
        return -1
