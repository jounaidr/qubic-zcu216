import numpy as np
from pynq import Overlay
import xrfclk
import xrfdc
import json
import time
import os
import glob
from qubic.rfsoc.bram import BramCfgs, vsign32


def vector(val):
    if isinstance(val,list) or isinstance(val,tuple) or isinstance(val, np.ndarray):
        vout = val
    else:
        vout = np.array([val])
    return vout

class PLInterface:
    """
    This class is a low level interface to RFSoC PL, and is intended to be run on the RFSoC 
    ZYNQ ARM core, configured with pyq 3.0. Uses a pynq overlay for PS-PL communication.
    """
    def __init__(self, commit_hash):
        """
        Parameters
        ----------
            commit_hash : str
                first 6 digits of gateware commit hash used to compile
                the XSA to load. xsa files (along with bram and reg json files)
                should be in rfsoc/bits/commit_hash.
        """
        commit_dir = os.path.join(os.path.dirname(__file__), 'bits', commit_hash)
        self.bram_cfgs = BramCfgs(os.path.join(commit_dir, 'bram.json'))
        with open(os.path.join(commit_dir, 'cfgregs.json')) as bjfp:
            self.cfgregs_cfg = json.load(bjfp)
        with open(os.path.join(commit_dir, 'dspregs.json')) as jfp:
            self.dspregs_cfg = json.load(jfp)
        with open(os.path.join(commit_dir, 'rfdc.json')) as fjson:
            self.rfdc_cfg = json.load(fjson)
        self.overlay = None
        self.fmem = {}
        self.nproc = len([name for name in self.bram_cfgs.keys() if name[:7] == 'command'])
        self.commit_dir = commit_dir

    def config_mts(self,dactiles=0xf,adctiles=0xf,daclatency=-1,adclatency=-1):
    # Set which RF tiles use MTS and turn MTS off
        self.rfdc.mts_dac_config.RefTile = 2  # tile 0 is the main reference - refer to restrictions
        self.rfdc.mts_adc_config.RefTile = 2
        self.rfdc.mts_dac_config.Target_Latency = daclatency
        self.rfdc.mts_adc_config.Target_Latency = adclatency
        self.rfdc.mts_dac_config.Tiles = 0xf #bitmask over tiles
        self.rfdc.mts_adc_config.Tiles = 0xf
        self.rfdc.mts_dac_config.SysRef_Enable = 1
        self.rfdc.mts_adc_config.SysRef_Enable = 1

    def mts(self,daclatency=260,adclatency=60):
        self.config_mts()
        self.rfdc.mts_dac()
        self.rfdc.mts_adc()
        dacmeaslatency=np.array([self.rfdc.mts_dac_config.Latency[i] for i in range(4)])
        adcmeaslatency=np.array([self.rfdc.mts_adc_config.Latency[i] for i in range(4)])
        if ((all(dacmeaslatency-dacmeaslatency[0]==0) and dacmeaslatency[0]<daclatency) 
                and (all(adcmeaslatency-adcmeaslatency[0]==0) and adcmeaslatency[0]<adclatency)):
            self.config_mts(daclatency=daclatency,adclatency=adclatency)
            self.rfdc.mts_dac()
            self.rfdc.mts_adc()
            dacmeaslatency=np.array([self.rfdc.mts_dac_config.Latency[i] for i in range(4)])
            adcmeaslatency=np.array([self.rfdc.mts_adc_config.Latency[i] for i in range(4)])
        return 0 if all(dacmeaslatency==daclatency) and all(adcmeaslatency==adclatency) else 1

    def adcnyquist(self,n=1):
        """
        Set nyquist zone to use for ADC configuration
        """
        if self.overlay is not None:
            rfdc = self.overlay.rf_data_converter
            for tile,block in self.rfdc_cfg['adctilechan']:
                rfdc.adc_tiles[tile].blocks[block].NyquistZone = n

    def dacnyquist(self,n=1):
        """
        Set nyquist zone to use for DAC configuration
        """
        if self.overlay is not None:
            rfdc = self.overlay.rf_data_converter
            for tile,block in self.rfdc_cfg['dactilechan']:
                rfdc.dac_tiles[tile].blocks[block].NyquistZone = n

    def load_overlay(self, xsafile=None, download=True):
        """
        Load gateware into FPGA PL
        """
        if xsafile is None:
            xsafile = glob.glob(os.path.join(self.commit_dir, 'psbd*.xsa'))[0]
        self.overlay = Overlay(xsafile, download=download)
        self.rfdc = self.overlay.rf_data_converter

    def refclks(self, lmk_freq, lmx_freq=0):
        xrfclk.set_ref_clks(lmk_freq=lmk_freq,lmx_freq=lmx_freq)

    def read(self, name, start_addr=0, stop_addr=None):
        """
        Read value from register or memory

        Parameters
        ----------
            name : str
                name of entity to read from, referenced to names in
                bram.json, cfgregs.json, and dspregs.json
            start_addr : int
                if BRAM, starting address to read from relative to base address
            stop_addr : int
                if BRAM, last address to read from 

        Returns
        -------
            val : int or np array
                if bram, returns a numpy array
                if reg, returns int
        """
        if name in self.bram_cfgs.keys():
            if self.bram_cfgs[name].access != 'read':
                raise Exception('BRAM {} does not have read access!'.format(name))

            start_addr += self.bram_cfgs[name].address
            if stop_addr is None:
                stop_addr = self.bram_cfgs[name].length
            else:
                if stop_addr > self.bram_cfgs[name].length:
                    raise Exception('Cannot read {} values from {} word \
                            memory'.format(stop_addr, self.bram_cfgs[name].length))
            stop_addr += self.bram_cfgs[name].address

            val = self.overlay.bramctrl.mmio.array[start_addr:stop_addr]

        elif name in self.dspregs_cfg.keys():
            val = self.overlay.dspregs.mmio.read(self.dspregs_cfg[name]['base_addr']*4)
        elif name in self.cfgregs.keys():
            val = self.overlay.cfgregs.mmio.read(self.cfgregs_cfg[name]['base_addr']*4)
        else:
            raise ValueError('could not find {}'.format(name))

        return val

    def write_cmd_buf(self, index, cmd_buf, start_addr=0):
        """
        Write single core command (instruction) memory

        Parameters
        ----------
            index : int or str
                core index to write
            cmd_list : list
                list of 128-bit command words to write
            start_addr : int
                starting address relative to base address
        """
        bufname = 'command' + str(index)
        addr = start_addr
        dt = np.dtype(np.uint32)
        dt = dt.newbyteorder('little')
        cmd_array = np.frombuffer(cmd_buf, dtype=dt)
        #self.overlay.bramctrl.mmio.array[start_addr : start_addr + len(cmd_array)] = cmd_array
        for i, cmd_word in enumerate(cmd_array):
            self.overlay.bramctrl.mmio.write((self.bram_cfgs[bufname].address + addr)*4, int(cmd_word))
            addr += 1

    def write_env_buf(self, elem_type, index, env_list, start_addr=0):
        """
        elem_type should be 'qdrv', 'rdrv', or 'rdlo'
        todo: add writes to Gang's bram objects
        """
        bufname = elem_type + 'env' + str(index)
        self.write_mem_buf(bufname, env_list, start_addr)

    def write_freq_buf(self, elem_type, index, env_list, start_addr=0):
        """
        elem_type should be 'qdrv', 'rdrv', or 'rdlo'
        """
        bufname = elem_type + 'freq' + str(index)
        self.write_mem_buf(bufname, env_list, start_addr)

    def write_mem_buf(self, name, mem_vals, start_addr=0):
        """
        General function for BRAM writes.

        Parameters
        ----------
            name : str
                name of BRAM (referenced to bram.json)
            mem_vals : list
                list of values to write
            start_addr : int
                start write addr relative to base_addr
        """
        #start_addr += self.bram_cfgs[name].address
        #self.overlay.bramctrl.mmio.array[start_addr : start_addr + len(mem_vals)] = mem_vals
        addr = start_addr
        mem_vals = np.frombuffer(mem_vals, dtype=np.uint32)
        for i, val in enumerate(mem_vals):
            val = int(val)
            assert self.bram_cfgs[name].access == 'write'
            assert 0 <= val < 2**self.bram_cfgs[name].paradict['Awidth']
            self.overlay.bramctrl.mmio.write((self.bram_cfgs[name].address + addr)*4, int(val))
            addr += 1

    def write_reg(self, name, value):
        """
        General function for writing registers.

        Parameters
        ----------
            name : str
                name of reg to write
            value : int
                value to write
        """
        if name in self.cfgregs_cfg.keys():
            self.overlay.cfgregs.mmio.write(self.cfgregs_cfg[name]['base_addr']*4, int(value))
        elif name in self.dspregs_cfg.keys():
            self.overlay.dspregs.mmio.write(self.dspregs_cfg[name]['base_addr']*4, int(value))
        else:
            raise ValueError('register {} not found'.format(name))

    def run_prog_acc(self, chanlist, nshots, readcnt=None, delay=0):
        """
        Trigger the proc cores to start a program, run it for nshots iterations,
        and read back the integrated IQ data from the acc buffers

        Parameters
        ----------
            chanlist : list
                list of channels to read from, referenced to proc_core/memory
                indices
            nshots : int
                number of shots to run. Program is restarted from the beginning 
                for each new shot
            readcnt : int
                number of values to read back from each accbuf. Defaults to nshots
            delay : int
                time to wait between starting program and reading back all results.
                Should be set to roughly nshots*circuit_execution_time

        Returns
        -------
            dict:
                Complex IQ shots for each accbuf in chanlist
        """
        self.write_reg('nshot', nshots)
        self.write_reg("resetacc", 1)
        self.write_reg("resetacc", 0)
        self.write_reg('start', 0)
        if readcnt is None:
            readcnt = nshots
        acc_iq = {}
        time.sleep(delay)
        for chan in chanlist:
            buf = 'accbuf{}'.format(chan)
            if readcnt is None:
                readcnt = self.bram_cfgs[buf].length//2
            readval = np.reshape(vsign32(self.read(buf, 0, readcnt*2).astype(int)), (-1, 2))
            acc_iq[chan] = 1j*readval[:, 0] + readval[:, 1]
        return acc_iq
