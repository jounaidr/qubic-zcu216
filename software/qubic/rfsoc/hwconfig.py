from distproc.hwconfig import ChannelConfig, ElementConfig, \
    FPGAConfig, load_channel_configs
import qubitconfig.envelope_pulse as ep
import distproc.command_gen as cg
try:
    import ipdb
except ImportError:
    print('warning: failed to import ipdb')
import numpy as np

class RFSoCElementCfg(ElementConfig):
    """
    TODO: figure out how to incorporate ADC chan here. some possibilities:
        - have a channel keyword to freq buffer and env buffer
        - remove DAC/ADC distinctions, just have sample period. each element
          can then have its own hwconfig object
    """
    def __init__(self, samples_per_clk=16, interp_ratio=1, env_max_samples=4095):
        self.env_n_bits = 16
        self.freq_n_bits = 32
        self.n_phase_bits = 17
        self.interp_ratio = interp_ratio
        self.env_max_samples = env_max_samples
        super().__init__(2.e-9, samples_per_clk)

    def get_freq_addr(self, freq_ind):
        return freq_ind

    def get_cfg_word(self, elem_ind, mode_bits=None):
        if mode_bits is not None: 
            raise Exception('mode not implemented')
        return elem_ind

    def get_freq_buffer(self, freqs):
        """
        Each frequency has 16 elements
            [0] is a 32-bit freq word
            [1:15] are 16 bit I MSB + 16 bit Q LSB
        """
        freq_buffer = np.empty(0)
        scale = 2**(self.freq_n_bits/2 - 1) - 1
        for freq in freqs:
            cur_freq_buffer = np.zeros(self.samples_per_clk)
            if freq is not None:
                cur_freq_buffer[0] = int(freq*2**self.freq_n_bits/self.fpga_clk_freq) & (2**self.freq_n_bits - 1)
                for i in range(1, self.samples_per_clk):
                    i_mult = int(round(np.cos(2*np.pi*freq*i*self.sample_period)*scale) % (2**(self.freq_n_bits/2)))
                    q_mult = int(round(np.sin(2*np.pi*freq*i*self.sample_period)*scale) % (2**(self.freq_n_bits/2)))
                    cur_freq_buffer[i] = (i_mult << (self.freq_n_bits//2)) + q_mult

            freq_buffer = np.append(freq_buffer, cur_freq_buffer)

        return freq_buffer

    def get_phase_word(self, phase):
        return int(((phase % (2*np.pi))/(2*np.pi) * 2**17))

    def get_env_word(self, env_ind, length_nsamples):
        if env_ind + length_nsamples > self.env_max_samples:
            raise Exception('{} exceeds max env length of {}'.format(env_ind + length_nsamples, self.env_max_samples))
        return env_ind//int(self.samples_per_clk/self.interp_ratio) \
                + (int(np.ceil(self.interp_ratio*length_nsamples/self.samples_per_clk)) << 12)

    def get_env_buffer(self, env):
        """
        Converts env to a list of samples to write to the env buffer memory.

        Parameters
        ----------
            env : np.ndarray, list, or dict
                if np.ndarray or list this is interpreted as a list of samples. Samples
                should be normalized to 1.

                if dict, a function in the qubitconfig.envelope_pulse library is used to
                calculate the envelope samples. env['env_func'] should be the name of the function,
                and env['paradict'] is a dictionary of attributes to pass to env_func. The 
                set of attributes varies according to the function but should include the 
                pulse duration twidth
        """
        if isinstance(env, np.ndarray) or isinstance(env, list):
            env_samples = np.asarray(env)
        elif isinstance(env, dict):
            dt = self.interp_ratio * self.sample_period
            env_func = getattr(ep, env['env_func'])
            _, env_samples = env_func(dt=dt, **env['paradict'])
            # ipdb.set_trace()
        else:
            raise TypeError('env must be dict or array')

        env_samples = np.pad(env_samples, (0, (self.samples_per_clk//self.interp_ratio - len(env_samples)
                % self.samples_per_clk//self.interp_ratio) % self.samples_per_clk//self.interp_ratio))

        return (cg.twos_complement(np.real(env_samples*(2**(self.env_n_bits-1)-1)).astype(int), nbits=self.env_n_bits) << self.env_n_bits) \
                    + cg.twos_complement(np.imag(env_samples*(2**(self.env_n_bits-1)-1)).astype(int), nbits=self.env_n_bits)

    def length_nclks(self, tlength):
        return int(np.ceil(tlength/self.fpga_clk_period))

    def get_amp_word(self, amplitude):
        return int(amplitude*(2**15 - 1))

