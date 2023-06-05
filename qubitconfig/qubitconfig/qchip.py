from qubitconfig import envelope_pulse

import inspect
import time
import copy
import json
import numpy as np
import re
try:
    import ipdb
except ImportError:
    print('warning: could not import ipdb')

VALID_PULSE_KEYS = ['pcarrier', 'fcarrier', 'dest', 't0', 'env', 'amp', 'twidth', 'gate']

class Qubit:
    """
    Simple class for storing qubit attributes

    Attributes
    ----------
        freq : float
            qubit drive frequency in Hz
        readfreq : float
            qubit readout resonator frequency in Hz
        additional attributes set by kwargs
    """
    def __init__(self, freq=None, readfreq=None, **kwargs):
        self.freq = freq
        self.readfreq = readfreq
        for k, v in kwargs.items():
            setattr(self, k, v)

class QChip:
    """
    Class containing configuration information for a chip described by a qchip json file
    (see examples/qubitcfg.json), as well as routines for calculating pulse envelopes. 

    Attributes
    ----------
        gates : dict
            dictionary of Gate objects, with keys corresponding to gate names in json config
        qubits : dict
            dictionary of Qubit objects
        gate_dict : dict
            dictionary of gate config information; key: gatename, value: list of pulse dicts
        cfg_dict : dict
            config dictionary
    """
    def __init__(self, cfg_dict):
        if isinstance(cfg_dict, str):
            with open(cfg_dict) as f:
                cfg_dict = json.load(f)

        self.qubits={}
        for k, v in cfg_dict['Qubits'].items():
            self.qubits.update({k:Qubit(**v)})

        self.gates = {}
        for k, pulselist in cfg_dict['Gates'].items():
            self.gates.update({k:Gate(pulselist, chip=self, name=k)})

    def save(self, wfilename):
        """
        Save self.cfg_dict in path wfilename
        """
        fwrite=open(wfilename, 'w')
        json.dump(self.cfg_dict, fwrite, indent=4)
        fwrite.close()

    def get_qubit_freq(self, freqname):
        """
        Get qubit frequency (could be read, drive, etc) from
        a qubit in the self.qubits dictionary.

        Parameters
        ----------
            freqname : str
                Frequency to get; format should be <QubitName>.<freqname>
        Returns
        -------
            float
                qubit frequency in Hz
        """
        if isinstance(freqname, str):
            m=re.match('(?P<qname>\S+)\.(?P<fname>\S+)', freqname)
            if m:
                q=m.group('qname')
                f=m.group('fname')
                if q in self.qubits:
                    if hasattr(self.qubits[q], f):
                        return getattr(self.qubits[q], f)

                    else:
                        raise AttributeError("Qubit %s doesn't have %s"%(str(q), str(f)))
                else:
                    raise AttributeError("Qubit %s not found"%str(q))

            else:
                raise Exception("%s does not match qubit.freqname format"%(str(freqname)))

        elif isinstance(freqname, float) or isinstance(freqname, int):
            return freqname #todo: do we actually want this to return int or should we do typechecking beforehand?

        else:
            raise TypeError("%s is not a string or number"%str(freqname))

    def getdest(self, destname):
        [q, d]=destname.split('.')
        return getattr(self.qubits[q], d)

    @property
    def qubit_dict(self):
        qdict = {}
        for name, obj in self.qubits.items():
            qdict[name] = vars(obj)
        return qdict

    @property
    def gate_dict(self):
        gdict = {}
        for name, obj in self.gates.items():
            gdict[name] = obj.cfg_dict
        return gdict

    @property
    def cfg_dict(self):
        return {'Qubits': self.qubit_dict, 'Gates': self.gate_dict}

    def update(self, keys_or_dict, value=None):
        """
        Update a qchip parameter using a tuple to list nested 
        attributes. E.g. to update the frequency of qubit Q0, use 
        ('Qubits', 'Q0', 'freq'). The function has two modes; either a set
        of key/value pairs can be given directly as a dict, or a 
        single key/value pair can be passed as separate parameters.

        Parameters
        ----------
            keys_or_dict: tuple, dict
                if tuple, then attribute access tuple; e.g.
                ('Qubits', 'Q0', 'freq').
                if dict, then key/value update dict; e.g.
                {('Qubits', 'Q0', 'freq'): 5.5e9}
            value: optional
                value to assign qchip parameter, if prev
                arg was a tuple of keys
        """
        if isinstance(keys_or_dict, tuple):
            self._update(keys_or_dict, value)
        elif isinstance(keys_or_dict, dict):
            for k, v in keys_or_dict.items():
                self._update(k, v)

    def _update(self, keys, value):
        if keys[0].lower() == 'qubits':
            assert len(keys)==3
            setattr(self.qubits[keys[1]], keys[2], value)
        elif keys[0].lower() == 'gates':
            assert len(keys)>=3
            gate = self.gates[keys[1]]
            gate.update(keys[2:], value)

    def add_gate(self, name, gate):
        """
        Add a new gate. 'gate' can be either Gate object or list of 
        dicts (i.e. json file entry). If Gate, then origininal object
        is copied, and parent chip reference is set to self.
        """
        if isinstance(gate, Gate):
            gate = copy.deepcopy(gate)
            gate.chip = self
            self.gates[name] = gate
        elif isinstance(gate, list):
            self.gates[name] = Gate(gate, self, name)

class Gate:
    """
    Describes a single or two-qubit gate. Primarily consists of a list of GatePulse
    and/or other Gate objects.

    Attributes
    ----------
        contents : list
            List of components that make up the gate. These are GatePulse objects or
            dictionaries describing either GatePulse objects or references to other Gates in parent QChip
        chip : QChip
            Reference to parent QChip object (can be None). This is used to dereference 
            any Gate objects in 'contents' when returning pulses.
        name : string
            Name of gate. Usually just the key in json file.
        tlenghth : float
            Returns total duration (in seconds) of gate
        cfg_dict : dict
            Returns human readable list of dicts describing contents
    Methods
    -------
        get_pulses
            Returns list of constituent pulses as GatePulse objects
    """
    def __init__(self, contents, chip, name):
        self.chip=chip
        self.name=name
        self._isread = None
        self.contents=[]

        for item in contents:
            if isinstance(item, GatePulse):
                gpulse = copy.deepcopy(item)
                gpulse.chip = self.chip
                gpulse.gate = self
                self.contents.append(gpulse) 
            elif isinstance(item, VirtualZ):
                self.contents.append(copy.deepcopy(item))
            elif 'gate' in item.keys():
                if item['gate'] == 'virtualz':
                    self.contents.append(VirtualZ(item.pop('freq'), item.pop('phase'), item.pop('qubit', None)))
                else:
                    self.contents.append(copy.deepcopy(item))
            else:
                self.contents.append(GatePulse(gate=self, chip=chip, **item))
    @property
    def tlength(self):
        return max([p.t0+p.twidth for p in self.get_pulses()]) - min([p.t0 for p in self.get_pulses()])

    @property
    def cfg_dict(self):
        cfg = []
        for item in self.contents:
            if isinstance(item, GatePulse) or isinstance(item, VirtualZ):
                cfg.append(item.cfg_dict)
            else:
                cfg.append(item)
        return cfg

    @property
    def isread(self):
        if self._isread is None:
            return np.any(np.array([pulse.dest.split('.')[1] == 'read' for pulse in self.get_pulses()]))
        else:
            return self._isread

    @isread.setter
    def isread(self, isread):
        self._isread = isread

    def get_updated_copy(self, keytup_or_dict, value=None):
        t0 = time.time()
        gate = self.copy()
        t1 = time.time()
        if isinstance(keytup_or_dict, tuple):
            updatedict = {keytup_or_dict : value}
        elif isinstance(keytup_or_dict, dict):
            updatedict = keytup_or_dict
        else:
            raise TypeError('unsupported type')

        for key_tuple, value in updatedict.items():
            gate.update(key_tuple, value)
        t2 = time.time()
        return gate

    def update(self, keys, value):
        assert isinstance(keys[0], int)
        content = self.contents[keys[0]]
        if isinstance(content, dict):
            keys = keys[1:]
            for i in range(len(keys)):
                if i == len(keys) - 1:
                    content[keys[i]] = value
                else:
                    content = content[keys[i]]
        elif isinstance(content, GatePulse):
            content.update(keys[1:], value)
        else:
            raise Exception('unsupported type')

    def get_norm(self, dt, ADC_FULLSCALE=32767):
        if self.isread:
            pulses = self.get_pulses()
            if len(pulses) != 2:
                raise Exception('Norm calculation assumes 1 up and 1 downconversion pulse')
            return np.sum(np.abs(ADC_FULLSCALE*pulses[0].get_env_samples(dt)[1]*pulses[1].get_env_samples(dt)[1]))
        else:
            raise Exception('Norm only implemented for readout-type gates. If this is a readout gate, set isread attribute')

    def get_pulses(self, gate_t0=0):
        """
        Returns a list of pulses (as GatePulse objects) that make up the gate. All 
        gates in 'contents' are broken down into constituent pulses. Returned GatePulses 
        are deep copied, but still contain a reference to parent QChip.

        Parameters
        ----------
            gate_t0 : start time of gate, which all pulses are referenced to
        Returns
        ------- 
            list
        """
        pulselist = []
        for item in self.contents:
            if isinstance(item, GatePulse):
                itemcpy = item.copy()
                itemcpy.t0 += gate_t0
                itemcpy.gate = self
                itemcpy.chip = self.chip
                pulselist.append(itemcpy)
            elif isinstance(item, VirtualZ):
                pulselist.append(item.copy())
            else:
                pulselist.extend(self.chip.gates[item['gate']].get_pulses(gate_t0))
        return pulselist

    def remove_virtualz(self):
        self.contents = [item for item in self.contents if not isinstance(item, VirtualZ)]

    def copy(self):
        """
        returns a deepcopy of self.contents (constituent pulses
        and gate refs), and a reference to the parent chip
        """
        cpycontents = []
        for content in self.contents:
            if isinstance(content, GatePulse) or isinstance(content, dict) or isinstance(content, VirtualZ):
                cpycontents.append(content.copy())
            else:
                raise TypeError

        return Gate(cpycontents, self.chip, self.name + '_cpy')

    def dereference(self):
        self.contents = self.get_pulses()


    #def pcalc(self, dt=0, padd=0, freq=None): #todo: what is this?
    #    return np.array([p.pcarrier+2*np.pi*(freq  if freq else p.fcarrier)*(dt+p.t0)+padd for p  in  self.get_pulses()])

class GatePulse:
    """
    Class describing an RF pulse. 

    Attributes
    ----------

    Methods
    -------
    """
    def __init__(self, pcarrier, fcarrier, dest=None, amp=None, t0=None, twidth=None, env=None, gate=None, chip=None):
        '''
        t0: pulse start time relative to the gate start time
        twidth: pulse env function parameter for the pulse width
        '''
        self.dest = dest 
        self._fcarrier = fcarrier
        self._pcarrier = pcarrier
        self.chip = chip
        self.gate = gate
        if env is not None and not isinstance(env, list):
            env = [env]
        self._env_desc = env
        self._env = None
        if amp is not None: 
            self.amp = amp
        if t0 is not None: 
            self.t0 = t0
        if twidth is not None: 
            self.twidth = twidth

    @property
    def env(self):
        """
        try lazy creation/loading of envelope
        """
        if not self._env and self._env_desc is not None:
            self._env = Envelope(self._env_desc)
        return self._env

    @env.setter
    def env(self, env):
        self._env = env

    def update(self, keys, value):
        if keys[0] == 'env':
            if hasattr(self, 'env'):
                self.env.update(keys[1:], value)
            else:
                self.env = Envelope(value)
        else:
            assert len(keys) == 1
            setattr(self, keys[0], value)
        

    def get_env_samples(self, dt):
        """
        Returns the pulse envelope sampled at dt

        Parameters
        ----------
            dt : float
                sampling interval in seconds
        Returns
        -------
            numpy array
        """
        return self.env.get_samples(dt, self.twidth, self.amp)

    @property
    def tend(self):
        return self.tstart + self.twidth

    @property
    def pcarrier(self):
        if isinstance(self._pcarrier, str):
            return eval(self._pcarrier.replace('numpy', 'np'))
        else:
            return self._pcarrier

    @pcarrier.setter
    def pcarrier(self, pcarrier):
        self._pcarrier = pcarrier

    @property
    def fcarrier(self):
        if isinstance(self._fcarrier, str):
            return self.chip.get_qubit_freq(self._fcarrier)
        else:
            return self._fcarrier

    @property
    def fcarriername(self):
        if isinstance(self._fcarrier, str):
            return self._fcarrier
        else:
            return None
    
    @fcarrier.setter
    def fcarrier(self, fcarrier):
        self._fcarrier = fcarrier

    @property
    def cfg_dict(self):
        #cfg = vars(self)
        cfg = {}
        cfg['fcarrier'] = self._fcarrier
        cfg['pcarrier'] = self._pcarrier
        if hasattr(self, 'dest'):
            cfg['dest'] = self.dest
        if hasattr(self, 'twidth'):
            cfg['twidth'] = self.twidth
        if hasattr(self, 't0'):
            cfg['t0'] = self.t0
        if hasattr(self, 'amp'):
            cfg['amp'] = self.amp
        if self._env_desc is not None:
            cfg['env'] = self._env_desc
        return cfg

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        #return hash(str(self.cfg_dict))
        return hash(str({k:self.cfg_dict[k] for k in ("amp", "twidth", "t0", "dest") if k in self.cfg_dict}))

    def timeoverlap(self, other):
        overlap=False
        if self.tstart<other.tstart:
            overlap=self.tend() < other.start
        else:
            overlap=other.tend() < self.tstart
        return overlap

    def copy(self):
        #return GatePulse(**self.cfg_dict, gate=self.gate, chip=self.chip)
        return GatePulse(**self.cfg_dict)


class Envelope:
    def __init__(self, env_desc):
        if not isinstance(env_desc, list):
            env_desc=[env_desc]
        self.env_desc=copy.deepcopy(env_desc)
        #self.env_desc = []
        #for env in env_desc:
        #    envdict = {}
        #    for k, v in env.items():
        #        if isinstance(v, dict):
        #            envdict[k] = v.copy()
        #        else:
        #            envdict[k] = v
        #    self.env_desc.append(envdict)


    def get_samples(self, dt, twidth, amp=1.0):
        samples = None
        tlist = None
        twidth = round(twidth, 10) #todo: why do we round this?

        for env in self.env_desc:
            ti, vali = getattr(envelope_pulse, env['env_func'])(dt=dt, twidth=twidth, **env['paradict'])
            if samples:
                samples *= vali
                assert np.all(ti==tlist)
            else:
                samples = vali
                tlist = ti

        samples *= amp

        return tlist, samples   

    def update(self, keys, value):
        env_desc = self.env_desc
        for i, key in enumerate(keys):
            if i == len(keys) - 1:
                env_desc[key] = value
            else:
                env_desc = env_desc[key]

    def __eq__(self, other):
        return sorted(self.env_desc) == sorted(other.env_desc)

class VirtualZ:
    """
    Attributes:
        qubit: qubitid
        freqname: freqname within qubit config to use
        freq to use is '<qubit>.<freqname>
        phase: phase in radians
    """

    def __init__(self, freqname, phase, qubit=None):
        if qubit is None:
            assert '.' in freqname
            self.qubit = freqname.split('.')[0]
            self.freqname = freqname.split('.')[1]

        else:
            self.qubit = qubit
            if '.' in freqname:
                self.freqname = freqname.split('.')[1]
            else:
                self.freqname = freqname

        self._phase = phase

    @property
    def global_freqname(self):
        return self.qubit + '.' + self.freqname

    @property
    def phase(self):
        if isinstance(self._phase, str):
            return eval(self._phase.replace('numpy', 'np'))
        else:
            return self._phase

    @property
    def cfg_dict(self):
        return {'gate': 'virtualz', 'freq': self.global_freqname, 'phase': self._phase}

    def copy(self):
        return copy.copy(self)


def convert_legacy_json(cfg_dict):
    if isinstance(cfg_dict, str):
        with open(cfg_dict) as f:
            cfg_dict = json.load(f)

    for gatename, gate in cfg_dict['Gates'].items():
        for i, pulse in enumerate(gate):
            # change gate strings to dict format
            if isinstance(pulse, str):
                gate[i] = {'gate': pulse}

            #reformat virtualz pulse
            elif 'env' not in pulse.keys() and 'gate' not in pulse.keys():
                zgate = {'gate': 'virtualz'}
                zgate['freq'] = pulse['fcarrier']
                zgate['phase'] = pulse['pcarrier']
                gate[i] = zgate

            # remove extraneous keys
            else:
                newpulse = {}
                for key, value in pulse.items():
                    if key in VALID_PULSE_KEYS:
                        newpulse[key] = value
                gate[i] = newpulse

    return cfg_dict

