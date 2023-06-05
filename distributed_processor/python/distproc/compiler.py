"""
Compiler layer for distributed processor. Program is input as a list of 
dicts encoding gates and processor instructions. Each instruction dict has a 
'name' key followed by other instruction specific keys. 

Instruction dict format:
    gate instructions: 
        {'name': gatename, 'qubit': [qubitid], 'modi': gate_param_mod_dict, 'reg_param': (pulseind, attribute, name)}

        gatename can be any named gate in the QChip object (qubitconfig.json), aside
        from names reserved for other operations described below. Named gate in QChip 
        object is gatename concatenated with qubitid (e.g. for the 'Q0read' gate you'd 
        use gatename='read' and qubitid='Q0'). 'modi' and 'reg_param' are optional.

    virtualz gates:
        {'name': 'virtualz', 'qubit': [qubitid], 'phase': phase_in_rad, 'freqname': fcarrier_name}
        {'name': 'virtualz', 'qubit': ['Q0'], 'freqname': 'freq_ef'}
        'Q0.freq_ef'

        'freqname' is optional; default is 'freq', which gets resolved into '<qubitid>.<freqname>' from qchip.
        This generally corresponds to the qubit drive frequency in the qchip file. Other frequencies include 
        readfreq and freq_ef.

        'phase' is phase in radians

    frequency declaration:
        {'name': 'declare_freq', 'freq': freq_in_Hz, scope: <list_of_qubits_or_channels>, 'freq_ind': <hw_index>}

        Declares a frequency to be used by the specified qubits or channels. 'freq_ind' can subsequently be 
        referenced by a register (i.e. if 'reg_param' is set to parameterize a pulse frequency). If 'freq_ind' 
        is not set in the instruction, it is inferred implicitly by incrementing the previous freq_ind, starting from 
        0. Note that scheduling a gate/pulse with a previously unused frequency will implicitly cause it to
        be declared in the assembly program.

    z-phase parameterization:
        By default, all z-gates are implemented in software; all X90, etc pulse phases are set according to
        the preceding z-gates, and the z-gate instructions are removed from the program. However, this
        is not always possible when z-gates need to be applied conditionally. A z-phase can be bound
        to a processor register using the following instruction:

        {'name': 'bind_phase', 'freq': fcarrier_name, 'var': reg_name}

        If this instruction is used, all z-gates applied to fcarrier_name (frequency referenced in qchip;
        e.g. Q0.freq, Q1.readfreq, etc), are done in realtime on the processor, and all pulses using
        fcarrier_name are phase parameterized by reg_name. reg_name must be declared separately.

        (this seems more like a compiler directive?)
        
    read fproc instruction:
        {'name': 'read_fproc', 'func_id': function_id, 'dest': var_name, 'scope': qubits}

        stores fproc result (next available from func_id) in variable var_name for use 
        later in the program.

    barrier: 
        {'name': 'barrier', 'qubits': qubitid_list}

        reference all subsequent gates to a common start time after the barrier (set by 
        the latest gate/measurement on any qubit in qubitid_list)

    sync: 
        {'name': 'sync', 'barrier_id': id, 'qubits': qubitid_list}

        synchronizes the gate time references between the cores corresponding to the qubits
        in qubitid_list.

    branch instructions: 
        {'name': 'branch_fproc', alu_cond: <'le' or 'ge' or 'eq'>, 'cond_lhs': <var or ival>, 
            'func_id': function_id, 'scope': <list_of_qubits> 'true': [instruction_list], 'false': [instruction_list]}
        branch directly on latest (next available) fproc result.

        {'name': 'branch_var', alu_cond: <'le' or 'ge' or 'eq'>, 'cond_lhs': <var or ival>, 
            'cond_rhs': var_name, 'scope': <list_of_qubits> 'true': [instruction_list], 'false': [instruction_list]}
        branch on variable

        {'name': 'loop', 'cond_lhs': <reg or ival>, 'cond_rhs': var_name, 'scope': <list_of_qubits>, 
            'body': [instruction_list]}
        repeats the instruction list 'body' when condition is true

    ALU instructions:
        {'name': 'alu', 'op': 'add' or 'sub' or 'le' or 'ge' or 'eq', 'lhs': var_name, 'rhs': var_name or value, 'out': output reg}

    variable declaration:
        {'name': declare, 'var': varname, 'dtype': int or phase or amp, 'scope': qubits}


    Note about instructions using function processor (FPROC): these instructions are scheduled
    immediately and use the next available function proc output. Which measurements are actually
    used for this depend on the configuration of the function processor. For flexibility, we don't 
    impose a particular configuration in this layer. It is the responsibilty of the programmer 
    to understand the configuration and schedule these instructions using appropriate delays, 
    etc as necessary.

    The measure/store instruction assumes an func_id mapping between qubits and raw measurements;
    this is not guaranteed to work across all FPROC implementations (TODO: maybe add software checks
    for this...)
"""

import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import copy
import logging 
try:
    import ipdb
except ImportError:
    logging.warning('failed to import ipdb')
import json
from collections import OrderedDict

import qubitconfig.qchip as qc
import distproc.assembler as asm
import distproc.hwconfig as hw

RESRV_NAMES = ['branch_fproc', 'branch_var', 'barrier', 'delay', 'sync', 
               'jump_i', 'alu', 'declare', 'jump_label', 'done',
               'jump_fproc', 'jump_cond', 'loop_end', 'loop']
INITIAL_TSTART = 5
DEFAULT_FREQNAME = 'freq'

class Compiler:
    """
    Class for compiling a quantum circuit encoded in the above format.
    Compilation stages:
        1. Determine the overall program scope (i.e. qubits used) as well
            as the scope of any declared variables
        2. Convert program to intermediate representation: at the moment,
            this is just flattening the control flow heirarchy to jump statements
        3. Construct basic blocks -- these are sections of code with linear 
            control flow (no branching/jumping/looping). In general, basic 
            blocks are scoped to some subset of qubits.
        4. Determine the control flow graph which outlines
            the possible control flow paths between the different basic blocks
            (for that qubit/proc core)
        5. Schedule all pulses
        6. Compile everything down to pulse level (CompiledProgram object)
    General usage:
        compiler = Compiler(...)
        compiler.schedule() # optional
        prog = compiler.compile()
    """
    def __init__(self, program, proc_grouping, fpga_config, qchip):
        """
        Parameters
        ----------
            program : list of dicts
                program to compile, in QubiC circuit format
            proc_grouping : str 
                if 'by_qubit', groups channels such that there is one core per
                qubit.
                if 'by_channel', groups channels such that there is one core per
                channel per qubit.
                if 'by_drive_ro', groups channels such that there is one core per
                drive channel per qubit, and another for both readout channels (per qubit)
            fpga_config : distproc.hwconfig.FPGAConfig object
                specifies FPGA clock period and execution time for relevant
                instructions
            qchip : qubitconfig.qchip.QChip object
                qubit calibration configuration; specifies constituent pulses
                for each native gate
        """
        self._fpga_config = fpga_config

        self.qchip = qchip

        if isinstance(program, list):
            self._from_list(program)

        else:
            raise TypeError('program must be of type list')

        self._scope_program()
        self._lint_and_scopevars()

        self.proc_group_type = proc_grouping
        self.proc_groups = generate_proc_groups(proc_grouping, self.qubits)

        self.zphase = {} #keys: Q0.freq, Q1.freq, etc; values: zphase
        self.chan_to_core = {} # maps qubit channels (e.g. Q0.qdrv) to core in asm dict
        for qubit in self.qubits:
            for chantype in ['qdrv', 'rdrv', 'rdlo']:
                chan = '{}.{}'.format(qubit, chantype)
                for grp in self.proc_groups:
                    if chan in grp:
                        self.chan_to_core[chan] = grp
                        break

            for freqname in qchip.qubit_dict[qubit].keys():
                self.zphase[qubit + '.' + freqname] = 0

        self._program_ir = generate_ir_program(self._program)
        self._make_basic_blocks()
        self._generate_cfg()

        self.is_scheduled = False


    def _make_basic_blocks(self):
        """
        Generates a dict of BasicBlock objects, stored in self._basic_blocks
        """
        self._basic_blocks = OrderedDict()
        self._basic_blocks['start'] = BasicBlock([], self.proc_group_type, self._fpga_config, self.qchip)
        self._basic_blocks['start'].qubit_scope = self.qubits

        cur_blockname = 'block_0'
        blockind = 1
        cur_block = []
        for statement in self._program_ir:
            if statement['name'] in ['jump_fproc', 'jump_cond', 'jump_i']:
                self._basic_blocks[cur_blockname] = BasicBlock(cur_block, self.proc_group_type, self._fpga_config, self.qchip)
                if statement['jump_label'].split('_')[-1] == 'loopctrl': #todo: break this out
                    ctrl_blockname = '{}_ctrl'.format(statement['jump_label'])
                else:
                    ctrl_blockname = '{}_ctrl'.format(cur_blockname)
                self._basic_blocks[ctrl_blockname] = BasicBlock([statement], self.proc_group_type, self._fpga_config, self.qchip)
                cur_blockname = 'block_{}'.format(blockind)
                blockind += 1
                cur_block = []
            elif statement['name'] == 'jump_label':
                self._basic_blocks[cur_blockname] = BasicBlock(cur_block, self.proc_group_type, self._fpga_config, self.qchip)
                cur_block = [statement]
                cur_blockname = statement['label']
            else:
                cur_block.append(statement)

        self._basic_blocks[cur_blockname] = BasicBlock(cur_block, self.proc_group_type, self._fpga_config, self.qchip)

        basic_blocks_nonempty = {}
        for blockname, block in self._basic_blocks.items():
            if not block.is_empty or blockname == 'start':
                basic_blocks_nonempty[blockname] = block

        self._basic_blocks = basic_blocks_nonempty

    def _generate_cfg(self):
        """
        Generates a global and per-qubit control flow graph of the (IR) program. 
        Graph is stored in a dictionary, where graph['source_block'] has a list 
        of destination block names.
        """
        self._control_flow_graph = {q: {'start': ['next_block']} for q in self.qubits}
        qubit_lastblock = {q: 'start' for q in self.qubits}
        for blockname, block in self._basic_blocks.items():
            for qubit in self.qubits:
                if qubit in block.qubit_scope:
                    #if qubit_lastblock[qubit] is not None:
                    #    self._control_flow_graph[qubit][qubit_lastblock[qubit]] = [blockname]

                    #if block.dest_nodes is not None:
                    #    self._control_flow_graph[qubit][blockname] = block.dest_nodes
                    #     qubit_lastblock[qubit] = None
                    # else:
                    #     qubit_lastblock[qubit] = blockname
                    if blockname == 'start':
                        continue
                    self._control_flow_graph[qubit][qubit_lastblock[qubit]] = \
                            [blockname if bname == 'next_block' else bname 
                                for bname in self._control_flow_graph[qubit][qubit_lastblock[qubit]]]
                    self._control_flow_graph[qubit][blockname] = block.dest_nodes
                    qubit_lastblock[qubit] = blockname #try this 

        self._global_cfg = {}
        for qubit in self.qubits:
            for block, dest in self._control_flow_graph[qubit].items():
                if 'next_block' in dest:
                    dest.remove('next_block')
                if block in self._global_cfg.keys():
                    self._global_cfg[block].extend(dest.copy())
                else:
                    self._global_cfg[block] = dest.copy()
        
        for block, dest in self._global_cfg.items():
            self._global_cfg[block] = list(set(dest))
                    

    def _get_cfg_predecessors(self):
        predecessors = {k: [] for k in self._basic_blocks.keys()}
        for node, dests in self._global_cfg.items():
            for dest in dests:
                # check for loops -- todo: break this out
                if dest.split('_')[-1] == 'loopctrl' and node.split('_')[-1] == 'ctrl':
                    continue
                predecessors[dest].append(node)

        return predecessors

    def schedule(self):
        block_end_times = {blockname: None for blockname in self._basic_blocks.keys()}
        block_end_times['start'] = {qubit: INITIAL_TSTART for qubit in self.qubits}
        cfg_predecessors = self._get_cfg_predecessors()
        self._basic_blocks['start'].schedule({}, {})
        node_queue = self._global_cfg['start'].copy()
        loop_dict = {}
        block_prev_loops = {blockname: {} for blockname in self._basic_blocks.keys()}
        block_prev_loops['start'] = {qubit: () for qubit in self.qubits}

        while node_queue:
            cur_node = node_queue.pop(0)
            cur_node_predecessors = cfg_predecessors[cur_node]
            pred_block_end_times = [block_end_times[node] for node in cur_node_predecessors]
            if None not in pred_block_end_times:
                block_start_times = {}
                for qubit in self._basic_blocks[cur_node].qubit_scope:
                    block_start_times[qubit] = []
                    block_prev_loops[cur_node][qubit] = ()
                    for node in cur_node_predecessors:
                        if qubit in self._basic_blocks[node].qubit_scope:
                            block_start_times[qubit].append(block_end_times[node][qubit])
                            #todo: consider breaking prev_loop timing analysis out into IR class
                            block_prev_loops[cur_node][qubit] += block_prev_loops[node][qubit] 
                    block_start_times[qubit] = max(block_start_times[qubit])
                    block_prev_loops[cur_node][qubit] = tuple(np.unique(block_prev_loops[cur_node][qubit]))

                self._basic_blocks[cur_node].schedule(block_start_times, block_prev_loops[cur_node])
                block_end_times[cur_node] = self._basic_blocks[cur_node].qubit_last_t

                if cur_node.split('_')[-1] == 'loopctrl': #start a loop
                    loop_dict[cur_node] = {'start_time': max([t for t in block_start_times.values()])}
                    block_prev_loops[cur_node] = {qubit: block_prev_loops[cur_node][qubit] + (cur_node,) 
                                                  for qubit in self._basic_blocks[cur_node].qubit_scope}

                elif cur_node[-13:] == 'loopctrl_ctrl':
                    # end loop
                    loopname = cur_node[:-5]
                    loop_dict[loopname]['delta_t'] = max(block_start_times.values()) - loop_dict[loopname]['start_time']
                    for qubit in self._basic_blocks[cur_node].qubit_scope:
                        block_end_times[cur_node][qubit] = loop_dict[loopname]['start_time']

                try:
                    node_queue.extend([node for node in self._global_cfg[cur_node] if not self._basic_blocks[node].is_scheduled])
                except KeyError:
                    pass
            else:
                node_queue.append(cur_node)

        self.loop_dict = loop_dict
        self.block_end_times = block_end_times
        self.is_scheduled = True

    def _from_list(self, prog_list):
        self._program = prog_list

    def _scope_program(self):
        self.qubits = []
        for statement in self._program:
            if 'qubit' in statement.keys():
                self.qubits.extend(statement['qubit'])
            if 'scope' in statement.keys():
                self.qubits.extend(statement['scope'])
        self.qubits = list(np.unique(np.asarray(self.qubits)))

    def _lint_and_scopevars(self):
        #todo: add in loop stuff here
        vars = {}
        for statement in self._program:
            if 'qubit' in statement.keys():
                assert isinstance(statement['qubit'], list)
            else: # this is not a gate
                assert statement['name'] in RESRV_NAMES

            if statement['name'] == 'declare':
                assert statement['var'] not in vars.keys()
                vars[statement['var']] = {'dtype': statement['dtype'], 'scope': statement['scope']}
            elif statement['name'] == 'alu':
                assert vars[statement['in1']]['dtype'] == vars[statement['out']]['dtype']
                assert set(vars[statement['out']]['scope']).issubset(vars[statement['in1']]['scope'])
                if isinstance(statement['in0'], str):
                    assert statement['in0']['dtype'] == vars[statement['out']]['dtype']
                    assert set(vars[statement['out']]['scope']).issubset(vars[statement['in0']]['scope'])
                statement['scope'] = vars[statement['out']]['scope']
            elif statement['name'] == 'barrier' or statement['name'] == 'delay':
                if 'qubit' not in statement.keys():
                    statement['qubit'] = self.qubits


    def compile(self):
        if not self.is_scheduled:
            self.schedule()
            logging.debug('done scheduling')
        asm_progs = {grp: [{'op': 'phase_reset'}] for grp in self.proc_groups}
        for blockname, block in self._basic_blocks.items():
            compiled_block = block.compile(self.loop_dict) # TODO: fix this so it's only on first block
            for proc_group in self.proc_groups:
                if proc_group in compiled_block.keys():
                    asm_progs[proc_group].extend(compiled_block[proc_group]) 

        for proc_group in self.proc_groups:
            asm_progs[proc_group].append({'op': 'done_stb'})

        return CompiledProgram(asm_progs, self._fpga_config)

    def _resolve_duplicate_jumps(self):
        #todo: write method to deal with multiple jump labels in a row
        pass


class BasicBlock:
    """
    Class for representing "basic blocks" in a qubic program. Basic blocks are program segments
    with linear control flow; i.e. they consist only of gate/barrier sequences. Each basic block
    is scoped to some subset of qubits used by the circuit. This class has methods for scheduling gates
    within the basic block and determining the total delta t.

    TODO:
        maybe add stuff for modifying program?
            - gate parameters
            - contents

    methods:
        schedule

    attributes:
        program : high-level qubic program
        scheduled_program: program with added execution time in 't' key
        delta_t: total execution time of basic block, in fpga clocks
    """

    def __init__(self, program, proc_grouping, fpga_config, qchip, swphase=True):
        self._program = program
        self._fpga_config = fpga_config
        self._scope()
        self.proc_group_type = proc_grouping
        self.zphase = {}
        for qubit in self.qubit_scope:
            for freqname in qchip.qubit_dict[qubit].keys():
                self.zphase[qubit + '.' + freqname] = 0
        self.is_resolved = False
        self.is_scheduled = False
        self.is_zresolved = not swphase
        self._swphase = swphase
        self.qchip = qchip
        if not swphase:
            raise Exception('HW phases not yet implemented!')

    @property
    def dest_nodes(self):
        if len(self._program) == 0:
            return ['next_block']
        elif self._program[-1]['name'] in ['jump_fproc', 'jump_cond']:
            return [self._program[-1]['jump_label'], 'next_block']
        elif self._program[-1]['name'] in ['jump_i']:
            return [self._program[-1]['jump_label']]
        else:
            return ['next_block']

    @property
    def is_empty(self):
        return len(self._program) == 0

    def _scope(self):
        self.qubit_scope = []
        for statement in self._program:
            if 'qubit' in statement.keys():
                self.qubit_scope.extend(statement['qubit'])
            elif 'scope' in statement.keys():
                self.qubit_scope.extend(statement['scope'])
        self.qubit_scope = list(np.unique(np.asarray(self.qubit_scope)))

    def schedule(self, qubit_last_t, qubit_loop_dict):
        """
        Parameters
        ----------
            qubit_last_t : dict of ints
                last scheduled operation for each qubit
            qubit_loop_dict : dict of tuples
                loops traversed by this qubit
        """
        if not self.is_resolved:
            self._resolve_gates()
            logging.debug('done resolving block')
        if not self.is_zresolved:
            self._resolve_virtualz_pulses()
            logging.debug('done z-resolving block')
        #qubit_last_t = {q: 0 for q in self.qubit_scope}

        qubit_last_t = qubit_last_t.copy()

        self.scheduled_program = []
        for gate in self.resolved_program:
            if isinstance(gate, dict):
                if gate['name'] == 'barrier':
                    qubit_max_t = max([qubit_last_t[qubit] for qubit in gate['qubit']])
                    for qubit in gate['qubit']:
                        qubit_last_t[qubit] = qubit_max_t
                elif gate['name'] == 'delay':
                    for qubit in gate['qubit']:
                        qubit_last_t[qubit] += self._get_pulse_nclks(gate['t'])
                elif gate['name'] == 'declare':
                    self.scheduled_program.append(gate)
                elif gate['name'] == 'alu':
                    for qubit in self.qubit_scope:
                        qubit_last_t[qubit] += self._fpga_config.alu_instr_clks
                    self.scheduled_program.append(gate)
                elif gate['name'] == 'jump_fproc':
                    for qubit in self.qubit_scope:
                        qubit_last_t[qubit] += self._fpga_config.jump_fproc_clks
                    self.scheduled_program.append(gate)
                elif gate['name'] == 'jump_i':
                    for qubit in self.qubit_scope:
                        qubit_last_t[qubit] += self._fpga_config.jump_fproc_clks #todo: change to jump_i_clks
                    self.scheduled_program.append(gate)
                elif gate['name'] == 'jump_cond':
                    for qubit in self.qubit_scope:
                        qubit_last_t[qubit] += self._fpga_config.jump_cond_clks
                    self.scheduled_program.append(gate)
                elif gate['name'] == 'jump_label':
                    self.scheduled_program.append(gate)
                elif gate['name'] == 'loop_end':
                    for qubit in self.qubit_scope:
                        qubit_last_t[qubit] += self._fpga_config.alu_instr_clks
                    self.scheduled_program.append(gate)
                else:
                    raise Exception('{} not yet implemented'.format(gate['name']))
                continue
            pulses = gate.get_pulses()
            loop_history = qubit_loop_dict[pulses[0].dest.split('.')[0]]
            min_pulse_t = []
            for pulse in pulses:
                qubit = pulse.dest.split('.')[0]
                assert qubit in self.qubit_scope
                assert qubit_loop_dict[qubit] == loop_history
                qubit_t = qubit_last_t[qubit]
                min_pulse_t.append(qubit_t - self._get_pulse_nclks(pulse.t0))
            gate_t = max(min_pulse_t)
            for pulse in pulses:
                qubit_last_t[pulse.dest[:2]] = max(qubit_last_t[pulse.dest[:2]], gate_t \
                        + self._get_pulse_nclks(pulse.t0) + max(self._get_pulse_nclks(pulse.twidth),
                        self._fpga_config.pulse_regwrite_clks))

            self.scheduled_program.append({'gate': gate, 't': gate_t})

        self.qubit_last_t = qubit_last_t
        self.is_scheduled = True

    def _resolve_gates(self):
        """
        convert gatedict references to objects, then dereference (i.e.
        all gate.contents elements are GatePulse or VirtualZ objects)
        """
        self.resolved_program = []
        for gatedict in self._program:
            if gatedict['name'] in RESRV_NAMES:
                self.resolved_program.append(gatedict)

            elif gatedict['name'] == 'virtualz':
                assert len(gatedict['qubit']) == 1
                self.resolved_program.append(qc.VirtualZ(gatedict.pop('freqname', DEFAULT_FREQNAME),
                                                         gatedict.pop('phase'), gatedict.pop('qubit')[0]))

            else:
                gatename = ''.join(gatedict['qubit']) + gatedict['name']
                gate = self.qchip.gates[gatename]
                if 'modi' in gatedict and gatedict['modi'] is not None:
                    gate = gate.get_updated_copy(gatedict['modi'])
                else:
                    gate = gate.copy()
                gate.dereference()
                self.resolved_program.append(gate)

        self.is_resolved = True

    def _get_pulse_nclks(self, length_secs):
        return int(np.ceil(length_secs/self._fpga_config.fpga_clk_period))

    def _resolve_virtualz_pulses(self):
        zresolved_program = []
        for gate in self.resolved_program:
            if isinstance(gate, qc.Gate):
                # gate = gate.copy()
                for pulse in gate.contents:
                    # TODO: fix config/encoding of these
                    if isinstance(pulse, qc.VirtualZ):
                        self.zphase[pulse.global_freqname] += pulse.phase
                    else:
                        if pulse.fcarriername is not None:
                            # TODO: figure out if this is intended behavior...
                            pulse.pcarrier += self.zphase[pulse.fcarriername]
                gate.remove_virtualz()
                if len(gate.contents) > 0:
                    zresolved_program.append(gate)

            elif isinstance(gate, qc.VirtualZ): 
                self.zphase[gate.global_freqname] += gate.phase

            else:
                zresolved_program.append(gate)

        self.resolved_program = zresolved_program

    def compile(self, loop_dict):
        """
        Converts gates to pulses, and all IR instructions to proc ASM code
        """
        # TODO: add twidth attribute to env, not pulse
        proc_groups_byqubit = generate_proc_groups(self.proc_group_type, self.qubit_scope, perqubit=True)
        proc_groups_flat = [grp for grouplist in proc_groups_byqubit.values() for grp in grouplist]
        proc_groups_bydest = {}
        for grp in proc_groups_flat:
            proc_groups_bydest.update({dest: grp for dest in grp})
        compiled_program = {grp: [] for grp in proc_groups_flat} 
        if not (self.is_resolved and self.is_scheduled):
            raise Exception('schedule and resolve gates first!')
        for i, instr in enumerate(self.scheduled_program):
            if 'gate' in instr.keys():
                for pulse in instr['gate'].get_pulses():
                    proc_group = proc_groups_bydest[pulse.dest]
                    envdict = pulse.env.env_desc[0]
                    if 'twidth' not in envdict['paradict'].keys():
                        envdict['paradict']['twidth'] = pulse.twidth
                    start_time = instr['t'] + self._get_pulse_nclks(pulse.t0)
                    compiled_program[proc_group].append(
                            {'op': 'pulse', 'freq': pulse.fcarrier, 'phase': pulse.pcarrier, 'amp': pulse.amp,
                             'env': pulse.env.env_desc[0], 'start_time': start_time, 'dest': pulse.dest})

            elif instr['name'] == 'jump_label':
                for q in instr['scope']:
                    for grp in proc_groups_byqubit[q]:
                        compiled_program[grp].append({'op': 'jump_label', 'dest_label': instr['label']})

            elif instr['name'] == 'done':
                for q in instr['scope']:
                    for grp in proc_groups_byqubit[q]:
                        compiled_program[grp].append({'op': 'done_stb'})

            elif instr['name'] == 'declare':
                for q in instr['scope']:
                    for grp in proc_groups_byqubit[q]:
                        compiled_program[grp].append({'op': 'declare_reg', 'name': instr['var'], 'dtype': instr['dtype']})

            elif instr['name'] == 'alu':
                for q in instr['scope']:
                    for grp in proc_groups_byqubit[q]:
                        compiled_program[grp].append({'op': 'reg_alu', 'in0': instr['lhs'], 'in1': instr['rhs'], 
                                                      'alu_op': instr['alu_op'], 'out_reg': instr['out']})

            elif instr['name'] == 'jump_fproc':
                statement = {'op': 'jump_fproc', 'in0': instr['cond_lhs'], 'alu_op': instr['alu_cond'], 
                             'jump_label': instr['jump_label'], 'func_id': instr['func_id']}
                for q in instr['scope']:
                    for grp in proc_groups_byqubit[q]:
                        compiled_program[grp].append(statement)

            elif instr['name'] == 'jump_cond':
                statement = {'op': 'jump_cond', 'in0': instr['cond_lhs'], 'alu_op': instr['alu_cond'], 
                             'jump_label': instr['jump_label'], 'in1': instr['cond_rhs']}
                for q in instr['scope']:
                    for grp in proc_groups_byqubit[q]:
                        compiled_program[grp].append(statement)

            elif instr['name'] == 'jump_i':
                statement = {'op': 'jump_i', 'jump_label': instr['jump_label']}
                for q in instr['scope']:
                    for grp in proc_groups_byqubit[q]:
                        compiled_program[grp].append(statement)

            elif instr['name'] == 'loop_end':
                statement = {'op': 'inc_qclk', 'in0': -loop_dict[instr['loop_label']]['delta_t']}
                for q in instr['scope']:
                    for grp in proc_groups_byqubit[q]:
                        compiled_program[grp].append(statement)

            else:
                raise Exception('{} not yet implemented'.format(instr['name']))
        return compiled_program

    def __repr__(self):
        return 'BasicBlock(' + str(self._program) + ')'


def generate_ir_program(program, label_prefix=''):
    """
    Generates an intermediate representation with control flow resolved into simple 
    conditional jump statements. This function is recursive to allow for nested control 
    flow structures.

    instruction format is the same as compiler input, with the following modifications:

    branch instruction:
        {'name': 'branch_fproc', alu_cond: <'le' or 'ge' or 'eq'>, 'cond_lhs': <var or ival>, 
            'func_id': function_id, 'scope': <list_of_qubits> 'true': [instruction_list_true], 'false': [instruction_list_false]}
    becomes:
        {'name': 'jump_fproc', alu_cond: <'le' or 'ge' or 'eq'>, 'cond_lhs': <var or ival>, 
            'func_id': function_id, 'scope': <list_of_qubits> 'jump_label': <jump_label_true>}
        [instruction_list_false]
        {'name': 'jump_i', 'jump_label': <jump_label_end>}
        {'name': 'jump_label',  'label': <jump_label_true>}
        [instruction_list_true]
        {'name': 'jump_label',  'label': <jump_label_end>}

    for 'branch_var', 'jump_fproc' becomes 'jump_cond', and 'func_id' is replaced with 'cond_rhs'

    .....

    loop:
        {'name': 'loop', 'cond_lhs': <reg or ival>, 'cond_rhs': var_name, 'scope': <list_of_qubits>, 
            'alu_cond': <'le' or 'ge' or 'eq'>, 'body': [instruction_list]}

    becomes:
        {'name': 'jump_label', 'label': <loop_label>}
        {'name': 'barrier', 'scope': <list_of_qubits>}
        [instruction_list]
        {'name': 'loop_end', 'scope': <list_of_qubits>, 'loop_label': <loop_label>}
        {'name': 'jump_cond', 'cond_lhs': <reg or ival>, 'cond_rhs': var_name, 'scope': <list_of_qubits>,
         'jump_label': <loop_label>, 'jump_type': 'loopctrl'}
        

    TODO: consider sticking this in a class
    """
    flattened_program = []
    branchind = 0
    for i, statement in enumerate(program):
        statement = copy.deepcopy(statement)
        if statement['name'] in ['branch_fproc', 'branch_var']:
            falseblock = statement['false']
            trueblock = statement['true']

            flattened_trueblock = generate_ir_program(trueblock, label_prefix='true_'+label_prefix)
            flattened_falseblock = generate_ir_program(falseblock, label_prefix='false_'+label_prefix)

            jump_label_false = '{}false_{}'.format(label_prefix, branchind)
            jump_label_end = '{}end_{}'.format(label_prefix, branchind)

            if statement['name'] == 'branch_fproc':
                jump_statement = {'name': 'jump_fproc', 'alu_cond': statement['alu_cond'], 'cond_lhs': statement['cond_lhs'],
                                  'func_id': statement['func_id'], 'scope': statement['scope']}
            else:
                jump_statement = {'name': 'jump_cond', 'alu_cond': statement['alu_cond'], 'cond_lhs': statement['cond_lhs'],
                                  'cond_rhs': statement['cond_rhs'], 'scope': statement['scope']}

            if len(flattened_trueblock) > 0:
                jump_label_true = '{}true_{}'.format(label_prefix, branchind)
                jump_statement['jump_label'] = jump_label_true
            else:
                jump_statement['jump_label'] = jump_label_end

            flattened_program.append(jump_statement)

            flattened_falseblock.insert(0, {'name': 'jump_label', 'label': jump_label_false, 'scope': statement['scope']})
            flattened_falseblock.append({'name': 'jump_i', 'jump_label': jump_label_end,
                                         'scope': statement['scope']})
            flattened_program.extend(flattened_falseblock)

            if len(flattened_trueblock) > 0:
                flattened_trueblock.insert(0, {'name': 'jump_label', 'label': jump_label_true, 'scope': statement['scope']})
            flattened_program.extend(flattened_trueblock)
            flattened_program.append({'name': 'jump_label', 'label': jump_label_end, 'scope': statement['scope']})

            branchind += 1

        elif statement['name'] == 'loop':
            body = statement['body']
            flattened_body = generate_ir_program(body, label_prefix='loop_body_'+label_prefix)
            loop_label = '{}loop_{}_loopctrl'.format(label_prefix, branchind)

            flattened_program.append({'name': 'jump_label', 'label': loop_label, 'scope': statement['scope']})
            flattened_program.append({'name': 'barrier', 'qubit': statement['scope']})
            flattened_program.extend(flattened_body)
            flattened_program.append({'name': 'loop_end', 'loop_label': loop_label, 'scope': statement['scope']})
            flattened_program.append({'name': 'jump_cond', 'cond_lhs': statement['cond_lhs'], 'cond_rhs': statement['cond_rhs'], 
                                      'alu_cond': statement['alu_cond'], 'jump_label': loop_label, 'scope': statement['scope']})
            branchind += 1

        elif statement['name'] == 'alu_op':
            statement = statement.copy()

        else:
            flattened_program.append(statement)

    return flattened_program

class CompiledProgram:
    """
    Simple class for reading/writing compiler output.

    Attributes:
        program : dict
            keys : proc group tuples (e.g. ('Q0.qdrv', 'Q0.rdrv', 'Q0.rdlo'))
                this is a tuple of channels that are driven by that proc core
            values : assembly program for corresponding proc core, in the format
                specified at the top of assembler.py. 

                NOTE: there is one deviation from this format; pulse commands 
                have a 'dest' field indicating the pulse channel, instead of
                an 'elem_ind'

        proc groups : list of proc group tuples

    TODO: metadata to consider adding:
        qchip version?
        git revision?
    """

    def __init__(self, program, fpga_config=None):
        self.fpga_config = fpga_config
        self.program = program

    @property
    def proc_groups(self):
        return self.program.keys()

    def save(self, filename):
        progdict = copy.deepcopy(self.program)
        if self.fpga_config is not None:
            progdict['fpga_config'] = self.fpga_config.__dict__

        with open(filename) as f:
            json.dumps(progdict, f, indent=4)

    def load(self, filename):
        raise NotImplementedError()


def load_compiled_program(filename):
    with open(filename) as f:
        progdict = json.load(f)

    return hw.FPGAConfig(**progdict['fpga_config'])


def generate_proc_groups(proc_grouping, qubits, perqubit=False):
    if proc_grouping == 'by_qubit':
        proc_grouping = {q: [('{}.qdrv'.format(q), '{}.rdrv'.format(q), '{}.rdlo'.format(q))] for q in qubits}
        # proc_grouping = [('{}.qdrv'.format(q), '{}.rdrv'.format(q), '{}.rdlo'.format(q)) for q in qubits]
    elif proc_grouping == 'by_channel':
        proc_grouping = {q: [('{}.qdrv'.format(q)), ('{}.rdrv'.format(q)), ('{}.rdlo'.format(q))] for q in qubits}

        # proc_grouping.extend([('{}.rdrv'.format(q)) for q in qubits])
        # proc_grouping.extend([('{}.rdlo'.format(q)) for q in qubits])
    elif proc_grouping == 'by_drive_ro':
        proc_grouping = {q: [('{}.qdrv'.format(q)), ('{}.rdrv'.format(q), '{}.rdlo'.format(q))] for q in qubits}
        # proc_grouping.extend([('{}.rdrv'.format(q), '{}.rdlo'.format(q)) for q in qubits])
    else:
        raise ValueError('{} group not supported'.format(proc_grouping))
    
    if not perqubit:
        proc_grouping = [group for grouplist in proc_grouping.values() for group in grouplist]

    return proc_grouping


