import numpy as np
import h5py
import fcntl

class SpikesArchive(object):
    def __init__(self, point):
        self.point = point
        self.path = self.point.spike_archive_path
    def open_hdf5_handle(self):
        return h5py.File(self.path)
    def load_attrs(self):
        with h5py.File(self.path) as hdf5_handle:
            self.attrs = dict(hdf5_handle.attrs)
    def get_spikes(self, cell_type='grc'):
        # no need to lock the archive or to save the file handle,
        # since we plan on using this in read-only mode.  TODO: this
        # actually needs to be revised, since ultimately we would like
        # to use the SpikesArchive object also in the compress.py
        # script, which means write-access as well. 
        self.load_attrs()
        n_cells = self.attrs['n_'+cell_type]
        start_time = self.point.sim_duration - self.point.ana_duration
        hdf5_handle = self.open_hdf5_handle()
        observation_list = [np.array(hdf5_handle['/{0:03d}/{1:02d}/{2}_spiketimes'.format(spn, tn, cell_type)]) for spn in range(self.point.n_stim_patterns) for tn in range(self.point.n_trials)]
        hdf5_handle.close()
        spikes = [[c[c>start_time].tolist() for c in o.transpose()] for o in observation_list]
        return spikes
    def get_spike_counts(self, cell_type='grc'):
        self.load_attrs()
        n_cells = self.attrs['n_'+cell_type]
        start_time = self.point.sim_duration - self.point.ana_duration
        hdf5_handle = self.open_hdf5_handle()
        observation_handles = [hdf5_handle['/{0:03d}/{1:02d}/{2}_spiketimes'.format(spn, tn, cell_type)] for spn in range(self.point.n_stim_patterns) for tn in range(self.point.n_trials)]
        spike_counts = np.array([[np.sum(c > start_time) for c in np.array(o).transpose()] for o in observation_handles])
        if spike_counts.dtype == np.dtype('O'):
            # network was completely silent for at least one
            # observation. We need to carefully loop over all
            # observations to avoid the problematic case
            print("archive {0}: found at least one completely silent observation.".format(self.path))
            spike_counts = np.zeros(shape=(len(observation_handles), n_cells))
            for n, oh in enumerate(observation_handles):
                ob = np.array(oh)
                if ob.size:
                    spike_counts[n] = np.sum(ob > start_time, axis=0)
        hdf5_handle.close()
        return spike_counts

    def get_stim_pattern(self, stim_pattern_number):
        self.load_attrs()
        hdf5_handle = self.open_hdf5_handle()
        pattern = np.asarray(hdf5_handle['/{0:03d}/stim_pattern'.format(stim_pattern_number)])
        hdf5_handle.close()
        return pattern
        
class ResultsArchive(object):
    def __init__(self, point):
        self.point = point
        self.path = "{0}/mi.hdf5".format(self.point.data_folder_path)
        self.datasets = ['tr_indexes',
                         'tr_linkage',
                         'tr_direct_mi',
                         'ts_decoded_mi_plugin',
                         'ts_decoded_mi_bootstrap',
                         'ts_decoded_mi_qe',
                         'ts_decoded_mi_pt',
                         'ts_decoded_mi_nsb',
                         'px_at_same_size_point',
                         'i_level_array',
                         'i_sparseness_hoyer',
                         'i_sparseness_activity',
                         'o_level_array',
                         'o_sparseness_hoyer',
                         'o_sparseness_activity',
                         'o_synchrony']
    def _is_archive_on_disk_complete(self):
        target_group = self._open()
        answer = all([ds in target_group.keys() for ds in self.datasets])
        self._close()
        return answer
    def _has_been_loaded(self):
        return all([hasattr(self.point, ds) for ds in self.datasets])
    def _open(self):
        # we need to create and remember a file handle and a file lock for the archive,
        #   to avoid concurrent writes by other analysis processes.
        self._lock = open(self.path, 'a')
        fcntl.lockf(self._lock, fcntl.LOCK_EX)
        self._hdf5_handle = h5py.File(self.path)
        nspg = self._hdf5_handle.require_group('sp%d' % self.point.n_stim_patterns)
        ntrg = nspg.require_group('t%d' % self.point.n_trials)
        sdurg = ntrg.require_group('sdur%d' % self.point.sim_duration)
        adurg = sdurg.require_group('adur%d' % self.point.ana_duration)
        trsg = adurg.require_group('train%d' % self.point.training_size)
        mixg = trsg.require_group('mix%.2f' % self.point.multineuron_metric_mixing)
        clmg = mixg.require_group('method_%s' % self.point.linkage_method_string)
        target_group = clmg.require_group('tau%d' % self.point.tau)
        return target_group
    def _close(self):
        self._hdf5_handle.close()
        fcntl.lockf(self._lock, fcntl.LOCK_UN)
    def _load_from_disk(self):
        if self._is_archive_on_disk_complete():
            # the analysis results we're looking for are in the corresponding hdf5 archive on disk
            target_group = self._open()
            for ds in self.datasets:
                setattr(self.point, ds, np.array(target_group[ds]))
            self._close()
            #self.point.decoder_precision = (1./self.point.tr_linkage)[:,2][::-1]
            self.point.point_mi_plugin = self.point.ts_decoded_mi_plugin[self.point.n_stim_patterns]
            self.point.point_mi_qe = self.point.ts_decoded_mi_qe[self.point.n_stim_patterns-1]
            #self.point.point_separation = 1./self.point.decoder_precision[self.point.n_stim_patterns-1]
            #self.point.o_level_entropy = entropy(self.point.o_level_hist_values/float(self.point.o_level_hist_values.sum()))
            #self.point.o_level_average_spiken = np.zeros(shape=(self.point.n_stim_patterns, self.point.n_grc))
            #self.point.sparseness_optimality = (1 - np.abs(self.point.o_population_sparseness-0.5))
            #self.point.new_measure =  self.point.sparseness_optimality * float(self.point.point_separation)
            #self.point.point_precision = self.point.decoder_precision[self.point.n_stim_patterns]
            return True
        else:
            # the hdf5 archive seems to be incomplete or missing
            return False
    def load(self):
        if self._has_been_loaded():
            # the results have been stored already in the corresponding Point object.
            return True
        else:
            # we need to load them from the hdf5 archive, if it exists
            return self._load_from_disk()
    def update_result(self, result_name, data):
        target_group = self._open()
        if result_name in target_group.keys():
            del target_group[result_name]
        target_group.create_dataset(result_name, data=data)
        self._close()
