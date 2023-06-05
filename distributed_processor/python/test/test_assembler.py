import pytest
import numpy as np
import ipdb
import distproc.assembler as asm 
import distproc.compiler as cm
import distproc.hwconfig as hw
import qubitconfig.qchip as qc
import qubitconfig.wiremap as wm

class ElementConfig(hw.ElementConfig):
    def __init__(self, samples_per_clk=16, interp_ratio=1):
        super().__init__(2.e-9, samples_per_clk)

    def get_freq_addr(self, freq):
        return 0xba

    def get_phase_word(self, phase):
        return int(phase/(2*np.pi)*256)

    def get_env_word(self, env_start_ind, env_length):
        return 0xdc

    def get_env_buffer(self, env_samples):
        return env_samples

    def get_freq_buffer(self, freqs):
        return np.zeros(10)

    def get_freq_addr(self, freq_ind):
        return 0x10

    def get_amp_word(self, amplitude):
        return 0x11

    def length_nclks(self, tlength):
        return int(np.ceil(tlength/self.fpga_clk_period))

    def get_cfg_word(self, elem_ind, mode_bits):
        return elem_ind

def test_prog_fromlist():
    asmlist = asm.SingleCoreAssembler([ElementConfig(), ElementConfig(), ElementConfig()])
    prog = []
    prog.append({'op':'phase_reset'})
    prog.append({'op':'reg_write', 'value':np.pi, 'name':'phase', 'dtype': ('phase', 0)})
    prog.append({'op': 'pulse', 'freq': 100e6, 'env': np.arange(10)/11., 'phase': 'phase', \
            'amp': 0.9, 'start_time': 15, 'elem_ind': 0, 'label': 'pulse0'})
    prog.append({'op':'done_stb'})

    asmlist.from_list(prog)
    cmdfl, envfl, freqfl = asmlist.get_compiled_program()

    asmprog = asm.SingleCoreAssembler([ElementConfig(), ElementConfig(), ElementConfig()])
    asmprog.add_phase_reset()
    asmprog.add_reg_write('phase', np.pi, ('phase', 0))
    asmprog.add_pulse(100e6, 'phase', 0.9, 15, np.arange(10)/11., 0, label='pulse0')
    asmprog.add_done_stb()
    cmdpr, envpr, freqpr = asmprog.get_compiled_program()

    assert np.all(np.asarray(cmdpr) == np.asarray(cmdfl))
    assert np.all(np.asarray(envpr[0]) == np.asarray(envfl[0]))
    assert np.all(np.asarray(freqpr) == np.asarray(freqfl))

def test_compiled_prog():
    prog = []
    prog.append({'op':'phase_reset'})
    prog.append({'op':'reg_write', 'value':np.pi, 'name':'phase', 'dtype': ('phase', 0)})
    prog.append({'op': 'pulse', 'freq': 100e6, 'env': np.arange(10)/11., 'phase': 'phase', \
            'amp': 0.9, 'start_time': 15, 'dest': 'Q0.qdrv', 'label': 'pulse0'})
    prog.append({'op':'done_stb'})

    progdict = {('Q0.qdrv', 'Q0.rdrv', 'Q0.rdlo'): prog}

    program = cm.CompiledProgram(progdict)
    globalasm = asm.GlobalAssembler(program, hw.load_channel_configs('channel_config.json'), ElementConfig)
    rawasm = globalasm.get_assembled_program()


