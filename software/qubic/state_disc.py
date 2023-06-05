"""
TODO: maybe add an abstract state disc class/interface. 
"""
from sklearn import mixture
import numpy as np
import pickle as pkl
import matplotlib.pyplot as plt
from distproc.hwconfig import load_channel_configs
from qubic.rfsoc.hwconfig import ChannelConfig
from abc import ABC, abstractmethod

class StateDiscriminator(ABC):

    @abstractmethod
    def fit(self, iqdata):
        pass

    @abstractmethod
    def predict(self, iqdata):
        pass

class GMMManager:
    """
    Class for managing multi-qubit GMM classifiers. 

    Attributes
    ----------
        chan_to_qubit : dict
            map from hardware channel (usually core_ind) to qubitid
        gmm_dict : dict
            dictionary of GMMStateDiscriminator objects. keys are qubitid

    """

    def __new__(cls, load_file=None, gmm_dict=None, chanmap_or_chan_cfgs=None):
        """
        Must specify either load_file, or chanmap_or_chan_cfgs. If load_file is NOT
        specified, can specify gmm_dict to load in existing set of GMM models.

        Parameters
        ----------
            load_file : str
                Loads GMM manager object from file (not yet implemented)
            gmm_dict : dict
                Existing GMM dictionary, indexed by qubit. Loads this into
                the object
            chanmap_or_chan_cfgs
                dict of ChannelConfig objects, or dictionary mapping 
                channels to qubits. 
        """
        if load_file is not None:
            assert gmm_dict is None
            with open(load_file, 'rb') as f:
                inst = pkl.load(f)
            if chanmap_or_chan_cfgs is not None:
                inst._resolve_chanmap(chanmap_or_chan_cfgs)
            return inst
        else:
            return super(GMMManager, cls).__new__(cls)


    def __init__(self, load_file=None, gmm_dict=None, chanmap_or_chan_cfgs=None):
        """
        Must specify either load_file, or chanmap_or_chan_cfgs. If load_file is NOT
        specified, can specify gmm_dict to load in existing set of GMM models.

        Parameters
        ----------
            gmm_dict : dict
                Existing GMM dictionary, indexed by qubit. Loads this into
                the object
            chanmap_or_chan_cfgs
                dict of ChannelConfig objects, or dictionary mapping 
                channels to qubits. 
        """
        if gmm_dict is not None:
            assert isinstance(gmm_dict, dict)
            assert load_file is None
            self.gmm_dict = gmm_dict
            assert chanmap_or_chan_cfgs is not None
            self._resolve_chanmap(chanmap_or_chan_cfgs)
        elif load_file is not None: #object was loaded from pkl
            assert gmm_dict is None
            if chanmap_or_chan_cfgs is not None:
                self._resolve_chanmap(chanmap_or_chan_cfgs)
        else:
            self.gmm_dict = {}
            assert chanmap_or_chan_cfgs is not None
            self._resolve_chanmap(chanmap_or_chan_cfgs)

    def _resolve_chanmap(self, chanmap_or_chan_cfgs):
        if isinstance(list(chanmap_or_chan_cfgs.values())[1], str):
            # this is a channel to qubit map
            self.chan_to_qubit = chanmap_or_chan_cfgs
        else:
            # this is a chan cfg dict
            self.chan_to_qubit = {str(chanmap_or_chan_cfgs[dest].core_ind): dest.split('.')[0] 
                                  for dest, channel in chanmap_or_chan_cfgs.items() 
                                  if isinstance(channel, ChannelConfig) and dest.split('.')[1] == 'rdlo'}

    def fit(self, iq_shot_dict):
        """
        Fit GMM models based on input data in iq_shot_dict. If model doesn't exist, create it,
        if so, update existing model with new data.
        """
        for chan, iq_shots in iq_shot_dict.items():
            if self._get_gmm_key(chan) in self.gmm_dict.keys():
                self.gmm_dict[self._get_gmm_key(chan)].fit(iq_shots)
            else:
                self.gmm_dict[self._get_gmm_key(chan)] = GMMStateDiscriminator(fit_iqdata=iq_shots)

    def _get_gmm_key(self, chan):
        if chan[0].lower() == 'q':
            return chan
        else:
            return self.chan_to_qubit[chan]

    def get_threshold_angle(self, qubit, label0=0, label1=1):
        return self.gmm_dict[qubit].get_threshold_angle(label0, label1)

    def predict(self, iq_shot_dict, output_keys='qubit'):
        """
        Assign labels to IQ shots.

        Parameters
        ----------
            iq_shot_dict : dict
                keys: channel no. or qubitid
                values: complex array of shots to predict
            output_keys : str
                either 'qubit' or 'channel'
        """
        result_dict = {}
        for chan, iq_shots in iq_shot_dict.items():
            if chan[0].lower() == 'q':
                result = self.gmm_dict[chan].predict(iq_shots)
                if output_keys == 'qubit':
                    result_dict[chan] = result
                elif output_keys == 'channel':
                    raise NotImplementedError
                else:
                    raise ValueError('output_keys must be qubit or channel')

            else:
                result = self.gmm_dict[self.chan_to_qubit[chan]].predict(iq_shots)
                if output_keys == 'qubit':
                    result_dict[self.chan_to_qubit[chan]] = result
                elif output_keys == 'channel':
                    result_dict[chan] = result
                else:
                    raise ValueError('output_keys must be qubit or channel')

        return result_dict

    def set_labels_maxtomin(self, iq_shot_dict, labels_maxtomin):
        """
        Batched version of GMMStateDiscriminator.set_labels_maxtomin

        Parameters
        ----------
            iq_shot_data : dict
                Set of complex IQ values
            labels_maxtomin : list
                Labels to assign in descending order of prevelance
        """
        for chan, iq_shots in iq_shot_dict.items():
            self.gmm_dict[self._get_gmm_key(chan)].set_labels_maxtomin(iq_shots, labels_maxtomin)

    def save(self, filename):
        with open(filename, 'wb') as f:
            pkl.dump(self, f)

class GMMStateDiscriminator:
    
    def __init__(self, load_file=None, n_states=2, fit_iqdata=None):
        self.labels = np.array(range(n_states))
        self.n_states = n_states
        self.fit_iqpoints = np.empty((0,), dtype=np.complex128)
        self.gmmfit = None
        if fit_iqdata is not None:
            self.fit(fit_iqdata)

    def fit(self, iqdata, update=True):
        """
        Fit GMM model (determine blob locations and uncertainties) based
        on input iqdata.

        Parameters
        ----------
            iqdata : np.ndarray
                array of complex-valued IQ shots
            update : bool
                if True (default), then update existing model with new 
                data, else re-create model using only new data for fit
        """
        if update:
            self.fit_iqpoints = np.append(self.fit_iqpoints, iqdata)
        else:
            self.fit_iqpionts = iqdata

        self.gmmfit = mixture.GaussianMixture(self.n_states)
        self.gmmfit.fit(self._format_complex_data(self.fit_iqpoints))

    def predict(self, iqdata):
        """
        Label iqdata with qubit state as determined by 
        """
        predictions = self.gmmfit.predict(self._format_complex_data(iqdata))
        return np.reshape(self.labels[predictions], iqdata.shape)

    def _format_complex_data(self, data):
        return np.vstack((np.real(data.flatten()), np.imag(data.flatten()))).T

    def set_labels(self, labels):
        if len(labels) != self.n_states:
            raise Exception('Must have {} labels!'.format(self.n_states))
        self.labels = np.asarray(labels)

    def get_threshold_angle(self, label0=0, label1=1):
        blob0_coords = self.gmmfit.means_[self.labels==label0][0]
        blob1_coords = self.gmmfit.means_[self.labels==label1][0]
        threshpoint = (blob0_coords + blob1_coords)/2
        return np.arctan2(threshpoint[1], threshpoint[0])

    def switch_labels(self):
        """
        Switch 1 and 0 labels. For higher energy states, reverse the order of
        the labels array.
        """
        self.labels = self.labels[::-1]

    def set_labels_maxtomin(self, iqdata, labels_maxtomin=[0,1]):
        """
        Set labels in descending order based on number of shots in a given blob.
        e.g. if labels_maxtomin = [0,1], this function will assign label 0
        to the GMM blob with the highest population in iqdata, and 1 to the next
        highest. If any rank-ordered blob should have unchanged assignment, set 
        to None. (e.g. labels_maxtomin=[None, 1] will only assign 1 to the lowest
        population blob)

        Parameters
        ----------
            iqdata : np.ndarray
                raw complex IQ shots
            labels_maxtomin : list or np.ndarray
                order of labels to assign, in descending order
                of prevelance in iqdata
        """
        assert len(labels_maxtomin) == self.n_states
        pred = self.gmmfit.predict(self._format_complex_data(iqdata))
        n_pred = [] #number of shots at 0, 1, 2, etc
        for i in range(self.n_states):
            n_pred.append(np.sum(pred == i))

        blobinds_sorted = np.argsort(n_pred)[::-1] #sort blobinds in order of max prevelance
        for i, label in enumerate(labels_maxtomin):
            if label is not None:
                self.labels[blobinds_sorted[i]] = label

