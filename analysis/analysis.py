import numpy as np
import h5py
import sys
import random
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist
import functools
import itertools
import pyentropy as pe
from matplotlib import pyplot as plt

sys.path.append("../")
from utils import data_archive_path_ctor, mi_archive_path_ctor

import pdb

TRAINING_RELATIVE_SIZE = .5

def loadspikes(grc_mf_ratio, n_grc_dend, network_scale, active_mf_fraction, bias, n_stim_patterns, n_trials, cell_type):
    
    archive_filename = data_archive_path_ctor(grc_mf_ratio, n_grc_dend, network_scale, active_mf_fraction, bias, n_stim_patterns, n_trials)
    archive = h5py.File(archive_filename)
    
    n_cells = archive['000']['00']['{0}_spiketimes'.format(cell_type)].shape[1]

    n_expcted_obs = n_stim_patterns * n_trials
    
    observation_list = [x[1]['{0}_spiketimes'.format(cell_type)] for s in archive.items() if isinstance(s[1], h5py.highlevel.Group) for x in s[1].items() if isinstance(x[1], h5py.highlevel.Group)]
    
    max_n_spikes = max([o.shape[0] for o in observation_list])

    spikes = -1 * np.ones(shape=(n_expcted_obs, n_cells, max_n_spikes))
    
    for k, o in enumerate(observation_list):
        spikes[k][:,0:o.shape[0]] = np.array(o).transpose()

    archive.close()
    return spikes

def convolve(obs_array, tau, dt):
    """Convolve with exponential kernel."""
    dt = float(dt)
    n_obs, n_cells, max_n_spikes = obs_array.shape
    kernel = np.exp(-np.arange(0, 10*tau, dt)/tau)
    kernel_length = 10*tau/dt
    n_bins = sim_length/dt
    conv = np.zeros(shape=(n_obs, n_cells, n_bins+kernel_length))

    for o, obs in enumerate(obs_array):
        for c, cell in enumerate(obs):
            for spike_index in [spike_time/dt for spike_time in cell[cell > 0]]:
                # here we could optimise this by writing it as a list comprehension, by using the .__add__ method
                conv[o, c, spike_index:spike_index+kernel_length] += kernel
    return conv

def multineuron_distance(p, q, c=0):
    delta = p-q
    E = np.dot(delta, delta.transpose())
    weighted_distances = E * (np.eye(E.shape[0]) + c*(np.ones_like(E) - np.eye(E.shape[0])))
    d = np.sqrt(weighted_distances.sum())
    if np.isnan(d):
        d = 0
    return d


## min_mf_number = int(sys.argv[1])
## grc_mf_ratio = float(sys.argv[2])
## n_grc_dend = int(sys.argv[3])
## network_scale = float(sys.argv[4])
## active_mf_fraction = float(sys.argv[5])
## bias = float(sys.argv[6])
## n_stim_patterns = int(sys.argv[7])
## n_trials = int(sys.argv[8])

min_mf_number = 6
grc_mf_ratio = 3
n_grc_dend = 4
network_scale = 1.00
active_mf_fraction = 0.5
bias = 20
n_stim_patterns = 20
n_trials = 20

sim_length = 300.
tau = 5.
dt = 2.
multineuron_metric_mixing = 0
cell_type = 'grc'

n_obs = n_stim_patterns * n_trials

# load data
spikes = loadspikes(grc_mf_ratio, n_grc_dend, network_scale, active_mf_fraction, bias, n_stim_patterns, n_trials, cell_type)
n_cells = spikes.shape[1]

# choose training and testing set: trials are picked at random, but every stim pattern is represented equally (i.e., get the same number of trials) in both sets. Trials are ordered with respect to their stim pattern.
n_tr_obs_per_sp = int(TRAINING_RELATIVE_SIZE * n_trials)
n_ts_obs_per_sp = n_trials - n_tr_obs_per_sp
train_idxs = list(itertools.chain(*([x+n_trials*sp for x in random.sample(range(n_trials), n_tr_obs_per_sp)] for sp in range(n_stim_patterns))))
test_idxs = [x for x in range(n_obs) if x not in train_idxs]
n_tr_obs = len(train_idxs)
n_ts_obs = len(test_idxs)
tr_input_signals = [int(x/n_trials) for x in train_idxs]
tr_spikes = spikes[train_idxs]
ts_spikes = spikes[test_idxs]

# convolve spike train to generate vector fields
tr_fields = convolve(tr_spikes, tau, dt)
ts_fields = convolve(ts_spikes, tau, dt)
n_timepoints = tr_fields.shape[2]

# prepare multineuron distance function by partial application and calculate distances
print('computing distances between training observations')
fixed_c_multineuron_distance = functools.partial(multineuron_distance, c=multineuron_metric_mixing)
tr_distances = []
for h in range(n_tr_obs):
    for k in range(h+1, n_tr_obs):
        tr_distances.append(fixed_c_multineuron_distance(tr_fields[h], tr_fields[k]))

# cluster training data
print('clustering training data')
tr_tree = linkage(tr_distances, method='weighted')

# compute mutual information by using direct clustering on training data
# --note: fcluster doesn't work in the border case with n_clusts=n_obs, as it never returns the trivial clustering. Cluster number 0 is never present in a clustering.
tr_direct_mi = np.zeros(n_tr_obs-1)
Xn = 1 # the output is effectively one-dimensional
Ym = n_stim_patterns
Ny = np.array([n_tr_obs_per_sp for each in range(n_stim_patterns)])
for n_clusts in range(1,n_tr_obs):
    Xm = n_clusts
    X = fcluster(tr_tree, t=n_clusts, criterion='maxclust') - 1 # cluster number 0 is never present in fcluster's output, so the elements of X live in [1,n_clusts] 
    X_dims = (Xn, Xm)
    s = pe.SortedDiscreteSystem(X, X_dims, Ym, Ny)
    s.calculate_entropies(method='plugin', sampling='naive', calc=['HX', 'HXY'])
    tr_direct_mi[n_clusts-1] = s.I()

# train the decoder and use it to calculate mi on the testing dataset
print("training the decoder and using it to calculate mi on test data")
relevant_tr_clusts = np.zeros(n_tr_obs+n_tr_obs-1)
# --first step: prepare the 'square part' of the distance matrix. special case for n_clusts==n_tr_obs.
relevant_tr_clusts = range(n_tr_obs)
tr_clustering = fcluster(tr_tree, t=n_tr_obs, criterion='maxclust')
out_alphabet = np.zeros(shape=(n_tr_obs+n_tr_obs-1, n_cells, n_timepoints))
out_alphabet[0:n_tr_obs] = tr_fields
distances = np.zeros(shape=(n_ts_obs, n_tr_obs+n_tr_obs-1))
for n, observation in enumerate(ts_fields):
    for m, symbol in enumerate(out_alphabet[relevant_tr_clusts]):
        distances[n,m] = fixed_c_multineuron_distance(observation, symbol)
# --now iterate over the number of clusters and, step by step, train the decoder and use it to calculate mi
ts_decoded_mi_plugin = np.zeros(n_tr_obs-1)
ts_decoded_mi_qe = np.zeros(n_tr_obs-1)
Ny = np.array([n_ts_obs_per_sp for each in range(n_stim_patterns)])
for n_clusts in range(n_tr_obs-1,0,-1):
    clust_idx = n_tr_obs + n_tr_obs - n_clusts - 1 # n_tr_obs, n_tr_obs+1, ..., n_tr_obs+n_tr_obs-2
    joined = tr_tree[clust_idx-n_tr_obs, 0:2]
    [relevant_tr_clusts.remove(c) for c in joined] # from now on, ingore clusters that have just been merged..
    relevant_tr_clusts.append(clust_idx) # ..but include the newly formed cluster in the next computations
    tr_clustering[tr_clustering==joined[0]] = clust_idx # this is to avoid calling fcluster again
    tr_clustering[tr_clustering==joined[1]] = clust_idx
    # compute new symbol as the weighted average of the joined clusters' centroids (that is, the centroid of the new cluster)
    # prepare weights for weighted average
    if joined[0] <= n_tr_obs:
        left_weight = 1
    else:
        left_weight = tr_tree[joined[0]-n_tr_obs][3]
    if joined[1] <= n_tr_obs:
        right_weight = 1
    else:
        right_weight = tr_tree[joined[1]-n_tr_obs][3]
    out_alphabet[clust_idx] = (out_alphabet[joined[0]] *  left_weight+ out_alphabet[joined[1]] * right_weight)/(left_weight + right_weight)
    # fill in the column in the distance matrix corresponding to the newly created symbol
    for n, observation in enumerate(ts_fields):
        distances[n, clust_idx] = fixed_c_multineuron_distance(observation, out_alphabet[clust_idx])
    # decode test data with the updated alphabet
    decoded_output = distances[:, relevant_tr_clusts].argmin(axis=1)
    # compute MI on the decoded data
    Xm = n_clusts
    X_dims = (Xn, Xm)
    X = decoded_output
    s = pe.SortedDiscreteSystem(X, X_dims, Ym, Ny)
    s.calculate_entropies(method='plugin', sampling='naive', calc=['HX', 'HXY'])
    ts_decoded_mi_plugin[n_clusts-1] = s.I()
    s.calculate_entropies(method='qe', sampling='naive', calc=['HX', 'HXY'], qe_method='plugin')
    ts_decoded_mi_qe[n_clusts-1] = s.I()    

# save analysis results in a separate file
mi_archive = h5py.File(mi_archive_path_ctor(grc_mf_ratio, n_grc_dend, network_scale, active_mf_fraction, bias))
spng = mi_archive.require_group(str(n_stim_patterns))
target_group = spng.require_group(str(n_trials))
datasets_to_be_deleted = [ds for ds in ['tr_direct_mi', 'ts_decoded_mi_plugin', 'ts_decoded_mi_qe'] if ds in target_group.keys()]
for ds in datasets_to_be_deleted:
    del target_group[ds]
target_group.create_dataset('tr_direct_mi', data=tr_direct_mi)
target_group.create_dataset('ts_decoded_mi_plugin', data=ts_decoded_mi_plugin)
target_group.create_dataset('ts_decoded_mi_qe', data=ts_decoded_mi_qe)    
mi_archive.close()

# plot
fig = plt.figure()
ax = fig.add_subplot(111)
ax.plot(tr_direct_mi, label='direct clustering on training data')
ax.plot(ts_decoded_mi_plugin, label='decoder: plugin')
ax.plot(ts_decoded_mi_qe, label='decoder: qe')
ax.plot([n_stim_patterns, n_stim_patterns], ax.get_ylim(), linestyle='--', color='black')
ax.legend(loc='lower right')
ax.set_xlabel('alphabet size (clusters in the decoder)')
ax.set_ylabel('MI (bits)')
if not n_stim_patterns in ax.get_xticks():
    ax.set_xticks(list(ax.get_xticks()) + [n_stim_patterns])
plt.show()
