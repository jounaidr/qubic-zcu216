import qubic.rfsoc.pl_interface as pl
import qubic.rfsoc.hwconfig as hw
import distproc.assembler as am
import numpy as np
import pdb
from tqdm import tqdm
from xmlrpc.client import Binary

ACC_BUF_SIZE = 1000

ELEM_CHAN_TYPES = ['qdrv', 'rdrv', 'rdlo']

class CircuitRunner:
    """
    Class for taking a program in binary/ASM form and running it on 
    the FPGA. Currently, this class is meant to be run on the QubiC FPGA 
    PS + pynq system. It will load and configure the specified PL bitfile,
    and can then be used to configure PL memory and registers, and read 
    back data from experiments.

    Attributes:
        _pl_driver : pl.PLInterface instance used for low level access
                     to memory and registers
        loaded_channels : list of channels with a program currently loaded
    """

    def __init__(self, platform='rfsoc', commit='81f773e5', load_xsa=True):
        if platform == 'rfsoc':
            self._pl_driver = pl.PLInterface(commit)
            self._pl_driver.load_overlay(download=load_xsa)
            self._pl_driver.refclks(lmk_freq=500.18)
            self._pl_driver.mts()
            self._pl_driver.dacnyquist(2)
            self._pl_driver.adcnyquist(1)
            self._pl_driver.write_reg('dspreset',0)
            self._pl_driver.write_reg("mixbb1sel",0)
            self._pl_driver.write_reg("mixbb2sel",0)
            self._pl_driver.write_reg("shift",12)
        else:
            raise Exception('rfsoc is the only implemented platform!')

        self.loaded_channels = []


    def load_and_run(self, rawasm, n_total_shots, reads_per_shot=1, delay_per_shot=500.e-6):
        """
        Load circuit described by rawasm "binary", then run for n_total_shots. 

        Parameters
        ----------
            rawasm : dict
            n_total_shots : int
                number of shots to run. Program is restarted from the beginning 
                for each new shot
            reads_per_shot : int
                number of values per shot per channel to read back from accbuf. Unless
                there is mid-circuit measurement involved this is typically 1
            delay_per_shot : float
                delay time (in seconds) per single shot of the circuit

        Returns
        -------
            dict:
                Complex IQ shots for each accbuf in chanlist; each array has 
                shape (n_total_shots, reads_per_shot)
        """
        self.load_circuit(rawasm)
        return self.run_circuit(n_total_shots, reads_per_shot, delay_per_shot)

    def load_circuit(self, rawasm, zero=True, load_commands=True, load_freqs=True, load_envs=True):
        """
        Load circuit described by rawasm "binary", which is the output of 
        the final distributed proc assembler stage. Loads command memory, env memory
        and freq buffer memory, according to specified input parameters. Before circuit is loaded, 
        if zero=True, all channels are zeroed out using zero_command_buf()

        Parameters
        ----------
            rawasm : dict
                keys are channels to load. For each channel, there should be:
                    'cmd_buf' : byte array containing compiled program binary
                    'env_buffers' : dict of env buffers for that channel:
                        0 : qdrv buffer
                        1 : rdrv buffer
                        2 : rdlo buffer
                    'freq_buffers' : dict of freq buffers for that channel:
                        0 : qdrv buffer
                        1 : rdrv buffer
                        2 : rdlo buffer
            zero : bool
                if True, (default), zero out all cmd buffers before loading circuit
            load_commands : bool
                if True, (default), load command buffers
            load_freqs : bool
                if True, (default), load freq buffers
            load_envs : bool
                if True, (default), load env buffers
        """
        if zero:
            self.zero_command_buf()
        for chan_key, chan_asm in rawasm.items():
            if load_commands:
                self.load_command_buf(chan_key, chan_asm['cmd_buf'])
            for i, chan_type in enumerate(ELEM_CHAN_TYPES): #todo: put these somewhere as parameters
                if load_envs:
                    self.load_env_buf(chan_type, chan_key, chan_asm['env_buffers'][i])
                if load_freqs:
                    self.load_freq_buf(chan_type, chan_key, chan_asm['freq_buffers'][i])

    def load_command_buf(self, core_key, cmd_buf):
        """
        Load cmd_buf into the command buffer of core core_key.

        Parameters
        ----------
            core_key : str
                str index of core mem to load
            cmd_buf : bytes or Binary
        """
        if isinstance(cmd_buf, Binary):
            cmd_buf = cmd_buf.data
        self._pl_driver.write_cmd_buf(core_key, cmd_buf)
        if core_key not in self.loaded_channels:
            self.loaded_channels.append(core_key)

    def zero_command_buf(self, core_keys=None):
        """
        Loads command memory with dummy asm program: reset phase, 
        output done signal, then idle. This is useful/necessary if 
        a new program is loaded on a subset of cores such that the 
        previous program is not completely overwritten (e.g. you 
        are loading a program that runs only on core 2, and the 
        previous program used cores 2 and 3).

        Parameters
        ----------
            core_keys : list
                list of channels (proc cores) to load. Defaults to
                all channels in currently loaded gateware.
        """
        if core_keys is None:
            core_keys = [str(i) for i in range(self._pl_driver.nproc)]

        rdrvelemcfg = hw.RFSoCElementCfg(16, 16)
        asm0 = am.SingleCoreAssembler([rdrvelemcfg, rdrvelemcfg, rdrvelemcfg])
        asm0.add_phase_reset()
        asm0.add_done_stb()
        cmd0, _, _ = asm0.get_compiled_program()

        for i in core_keys:
            self.load_command_buf(i, cmd0)

        for i in core_keys:
            if i in self.loaded_channels:
                self.loaded_channels.remove(i)

    def load_env_buf(self, chan_type, core_key, env_buf):
        """
        Load envelope buffer into specified chan_type (qdrv, rdrv, rdlo) 
        and core_key

        Parameters
        ----------
            chan_type : str
                'qdrv', 'rdrv', or 'rdlo'
            core_key : str
                str index of core mem to load
            env_buf : bytes or Binary
        """
        if isinstance(env_buf, Binary):
            env_buf = env_buf.data
        self._pl_driver.write_env_buf(chan_type, core_key, env_buf)

    def load_freq_buf(self, chan_type, core_key, freq_buf):
        """
        Load frequency buffer into specified chan_type (qdrv, rdrv, rdlo) 
        and core_key

        Parameters
        ----------
            chan_type : str
                'qdrv', 'rdrv', or 'rdlo'
            core_key : str
                str index of core mem to load
            freq_buf : bytes or Binary
        """
        if isinstance(freq_buf, Binary):
            freq_buf = freq_buf.data
        self._pl_driver.write_freq_buf(chan_type, core_key, freq_buf)

    def run_circuit_batch(self, raw_asm_list, n_total_shots, reads_per_shot=1, delay_per_shot=500.e-6,
                          reload_cmd=True, reload_freq=True, reload_env=True, zero_between_reload=True,
                          from_server=False):
        """
        Runs a batch of circuits given by a list of raw_asm "binaries". Each circuit is run n_total_shots
        times. reads_per_shot, n_total_shots, and delay_per_shot are passed directly into run_circuit, and must
        be the same for all circuits in the batch. The parameters reload_cmd, reload_freq, reload_env, and 
        zero_between_reload control which of these fields is rewritten circuit-to-circuit (everything is 
        rewritten initially). Leave these all at True (default) for maximum safety, to ensure that QubiC 
        is in a clean state before each run. Depending on the circuits, some of these can be turned off 
        to save time.

        TODO: consider throwing some version of all the args here into a BatchedCircuitRun or somesuch
        object

        Parameters
        ----------
            raw_asm_list : list
                list of raw_asm binaries to run
            n_total_shots : int
                number of shots per circuit
            reads_per_shot : int
                number of values per shot per channel to read back from accbuf. Unless
                there is mid-circuit measurement involved this is typically 1
            delay_per_shot : float
                delay time (in seconds) per single shot of the circuit
            reload_cmd : bool
                if True, reload command buffer between circuits
            reload_freq : bool
                if True, reload freq buffer between circuits
            reload_env: bool
                if True, reload env buffer between circuits
            from_server : bool
                set to true if calling over RPC. If True, pack returned s11 arrays into
                byte objects
        Returns
        -------
            dict:
                Complex IQ shots for each accbuf in chanlist; each array has 
                shape (len(raw_asm_list), n_total_shots, reads_per_shot)
        """
        s11 = {ch: np.zeros((len(raw_asm_list), n_total_shots, reads_per_shot), 
                            dtype=np.complex128) for ch in raw_asm_list[0].keys()}
        #TODO: using the channels in the first raw_asm_list elem is hacky, should figure out
        # a better way to initialize
        for i, raw_asm in enumerate(tqdm(raw_asm_list)):
            if i==0:
                self.load_circuit(raw_asm, True, True, True, True)
            else:
                self.load_circuit(raw_asm, zero=zero_between_reload, load_commands=reload_cmd,
                                  load_freqs=reload_freq, load_envs=reload_env)
            s11_i = self.run_circuit(n_total_shots, reads_per_shot, delay_per_shot)
            for ch in s11_i.keys():
                s11[ch][i] = s11_i[ch]

        if from_server:
            for ch in s11.keys():
                s11[ch] = s11[ch].tobytes()

        return s11


    def run_circuit(self, n_total_shots, reads_per_shot=1, delay_per_shot=500.e-6, from_server=False):
        """
        Run the currently loaded program and acquire integrated IQ shots. Program is
        run n_total_shots times, in batches of size shots_per_run (i.e. shots_per_run runs of the program
        are executed in logic before each readback/restart cycle). The current gateware 
        is limited to ~1000 reads in its IQ buffer, which generally means 
        shots_per_run = 1000//reads_per_shot

        Parameters
        ----------
            n_total_shots : int
                number of shots to run. Program is restarted from the beginning 
                for each new shot
            reads_per_shot : int
                number of values per shot per channel to read back from accbuf. Unless
                there is mid-circuit measurement involved this is typically 1
            delay_per_shot : float
                delay time (in seconds) per single shot of the circuit
            from_server : bool
                set to true if calling over RPC. If True, pack returned s11 arrays into
                byte objects

        Returns
        -------
            dict:
                Complex IQ shots for each accbuf in chanlist; each array has 
                shape (n_total_shots, reads_per_shot)
        """
        shots_per_run = min(ACC_BUF_SIZE//reads_per_shot, n_total_shots)
        n_runs = int(np.ceil(n_total_shots/shots_per_run))
        s11 = {ch: np.zeros((shots_per_run*n_runs, reads_per_shot), dtype=np.complex128) for ch in self.loaded_channels}
        delay = delay_per_shot*shots_per_run
        for i in range(n_runs):
            result = self._pl_driver.run_prog_acc(self.loaded_channels, shots_per_run, readcnt=reads_per_shot*shots_per_run, delay=delay)
            for ch in self.loaded_channels:
                s11[ch][i*shots_per_run : (i + 1)*shots_per_run, :] = result[ch].reshape((shots_per_run, reads_per_shot))

        #remove extraneous data
        if shots_per_run*n_runs > n_total_shots:
            for ch in self.loaded_chanels:
                s11[ch] = s11[ch][:n_total_shots]

        if from_server:
            for ch in self.loaded_channels:
                s11[ch] = s11[ch].tobytes()

        return s11
