import xmlrpc.client
import numpy as np

class CircuitRunnerClient:
    """
    CircuitRunner instance that can be run from a remote machine (i.e. not on
    the RFSoC ARM core) over RPC. Should be a drop-in replacement for 
    CircuitRunner for most experiments. Exposes the following methods from
    CircuitRunner:
        run_circuit
        run_circuit_batch
        load_circuit
    """

    def __init__(self, ip, port=9095):
        self.proxy = xmlrpc.client.ServerProxy('http://' + ip + ':' + str(port), allow_none=True)

    def run_circuit(self, n_total_shots, reads_per_shot=1, delay_per_shot=500.e-6):
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

        Returns
        -------
            dict:
                Complex IQ shots for each accbuf in chanlist; each array has 
                shape (n_total_shots, reads_per_shot)
        """
        s11 = self.proxy.run_circuit(n_total_shots, reads_per_shot, float(delay_per_shot), True)
        for ch in s11.keys():
            s11[ch] = np.reshape(np.frombuffer(s11[ch].data, dtype=np.complex128), 
                                 (n_total_shots, reads_per_shot))
        return s11

    def run_circuit_batch(self, raw_asm_list, n_total_shots, reads_per_shot=1, delay_per_shot=500.e-6,
                          reload_cmd=True, reload_freq=True, reload_env=True, zero_between_reload=True):
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
        Returns
        -------
            dict:
                Complex IQ shots for each accbuf in chanlist; each array has 
                shape (len(raw_asm_list), n_total_shots, reads_per_shot)
        """
        
        s11 = self.proxy.run_circuit_batch(raw_asm_list, n_total_shots, reads_per_shot, float(delay_per_shot),
                                     reload_cmd, reload_freq, reload_env, zero_between_reload, True)
        for ch in s11.keys():
            s11[ch] = np.reshape(np.frombuffer(s11[ch].data, dtype=np.complex128), 
                                 (len(raw_asm_list), n_total_shots, reads_per_shot))
        return s11

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
        self.proxy.load_circuit(rawasm, zero, load_commands, load_freqs, load_envs)
