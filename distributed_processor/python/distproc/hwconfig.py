"""
"""
from abc import ABC, abstractmethod
import distproc.command_gen as cg
import numpy as np
import json

class ElementConfig(ABC):
    """
    TODO: standardize constructor args for GlobalAssembler usage
    """

    def __init__(self, fpga_clk_period, samples_per_clk):
        self.fpga_clk_period = fpga_clk_period
        self.samples_per_clk = samples_per_clk

        #TODO: move these out of this class:
        self.nclks_alu = 2
        self.nclks_br_fproc = 2
        self.nclks_read_fproc = 2
        self.elems_per_core = 3

    @property
    def sample_period(self):
        return self.fpga_clk_period/self.samples_per_clk

    @property
    def sample_freq(self):
        return 1/self.sample_period

    @property
    def fpga_clk_freq(self):
        return 1/self.fpga_clk_period

    @abstractmethod
    def get_phase_word(self, phase):
        pass

    @abstractmethod
    def length_nclks(self, tlength):
        pass

    @abstractmethod
    def get_env_word(self, env_start_ind, env_length):
        pass

    @abstractmethod
    def get_env_buffer(self, env):
        pass

    @abstractmethod
    def get_freq_buffer(self, freqs):
        pass

    @abstractmethod
    def get_freq_addr(self, freq_ind):
        pass

    @abstractmethod
    def get_cfg_word(self, elem_ind, mode_bits):
        pass

    @abstractmethod
    def get_amp_word(self, amplitude):
        pass


class FPGAConfig:

    def __init__(self, **kwargs):
        self.fpga_clk_period = kwargs.pop('fpga_clk_period')
        self.alu_instr_clks = kwargs.pop('alu_instr_clks')
        self.jump_cond_clks = kwargs.pop('jump_cond_clks')
        self.jump_fproc_clks = kwargs.pop('jump_fproc_clks')
        self.pulse_regwrite_clks = kwargs.pop('pulse_regwrite_clks')

    @property
    def fpga_clk_freq(self):
        return 1/self.fpga_clk_period


class ChannelConfig:
    
    def __init__(self, core_ind, elem_ind, elem_params, env_mem_name, freq_mem_name, acc_mem_name):
        self.core_ind = core_ind
        self.elem_ind = elem_ind
        self.elem_params = elem_params
        self.env_mem_name = env_mem_name.format(core_ind=self.core_ind)
        self.freq_mem_name = freq_mem_name.format(core_ind=self.core_ind)
        self.acc_mem_name = acc_mem_name.format(core_ind=self.core_ind)


def load_channel_configs(config_dict):

    if isinstance(config_dict, str):
        with open(config_dict) as f:
            config_dict = json.load(f)

    assert 'fpga_clk_freq' in config_dict.keys()

    channel_configs = {}

    for key, value in config_dict.items():
        if isinstance(value, dict):
            channel_configs[key] = ChannelConfig(**value)

        else:
            channel_configs[key] = value 

    return channel_configs
