import numpy as np
import json


def sign16(v):
    #return int(v-65536) if (v>>15)&1 else v
    return signval(v, 16)


def sign32(v):
    return signval(v, 32)


def signval(v, width=16):
    return int(v-2**width) if (v>>(width-1))&1 else v


vsign16 = np.vectorize(sign16)
vsign32 = np.vectorize(sign32)


class BramCfgs(dict):
    def __init__(self, jsonfilename):
        with open(jsonfilename) as jfile:
            bramjson = json.load(jfile)
        for name, paradict in bramjson.items():
            super().__setitem__(name, BramCfg(name, paradict))


class BramCfg:
    def __init__(self, name, paradict):
        self.name=name
        self.paradict=paradict
        self.paradict['length'] = self.length

    @property
    def length(self):
        return int(self.paradict['Adepth'] if self.paradict['access']=='r' else self.paradict['Awidth']*self.paradict['Adepth']/self.paradict['Bwidth'])

    @property 
    def address(self):
        return int(str(self.paradict['address']), 0)
    
    @property
    def access(self):
        """
        Memory access mode. This is SWAPPED from the config 
        file, since that file is referenced to PL, not PS/software
        """
        if self.paradict['access'] == 'r':
            return 'write'
        elif self.paradict['access'] == 'w':
            return 'read'
        else:
            return None

    #def get_value(self, offset=None):
    #    return self._value if offset is None else self._value[offset]

    #def get_value16(self):
    #    value16_2 = np.zeros((self.length, 2), dtype=int)
    #    value16_2[:, 0] = self._value & 0xffff
    #    value16_2[:, 1] = (self._value >> 16) & 0xffff
    #    value16=value16_2.reshape((-1))
    #    return vsign16(value16)

    #def get_value32xy(self):
    #    svalue32=vsign32(self._value)
    #    return svalue32.reshape((-1, 2))

    #def zero(self):
    #    self._value=np.zeros(self.paradict['length'], dtype=int)

