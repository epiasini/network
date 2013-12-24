#! /usr/bin/env python
# -*- coding: utf-8 -*-
import time
from math import factorial

from utils.queue import BatchManager
from utils.parameters import ParameterSpace
from utils.parameters import PSlice as psl

#++++general controls+++++
force_rerun_simulations = False
clean_up_simulation_files = True

#+++++parameter ranges+++++++++++++
n_grc_dend = psl(4, 11, 1)
connectivity_rule = psl(0) # 0: tissue model, 1: random bipartite graph
input_spatial_correlation_scale = psl(0) # 0: uncorrelated
active_mf_fraction = psl(.1,1.,.1)
extra_tonic_inhibition = psl(0)
stim_rate_mu = psl(80)
stim_rate_sigma = psl(0)
noise_rate_mu = psl(10)
noise_rate_sigma = psl(0)
n_stim_patterns = psl(128)
n_trials = psl(50)
sim_duration = psl(150.0)
ana_duration = psl(150.0) # must be < min(sim_duration)
training_size = psl(5) # must be < min(n_trials)
multineuron_metric_mixing = psl(0.)
linkage_method = psl(1) # 0: ward, 1: kmeans
tau = psl(5)
dt = psl(2)

#----parameter consistency check
if training_size.realstop > n_trials.start:
    raise Exception("Decoder training set size must always be smaller than the number of trials!")
if ana_duration.realstop > sim_duration.start:
    raise Exception("Simulation length must always be greater than analysis time window!")

#---parameter space creation
parameter_space = ParameterSpace(sim_duration,
                                 min_mf_number,
                                 grc_mf_ratio,
                                 n_grc_dend,
                                 network_scale,
                                 active_mf_fraction,
                                 bias,
                                 stim_rate_mu,
                                 stim_rate_sigma,
                                 noise_rate_mu,
                                 noise_rate_sigma,
                                 n_stim_patterns,
                                 n_trials,
                                 training_size,
                                 multineuron_metric_mixing,
                                 linkage_method,
                                 tau,
                                 dt)

batch_manager = BatchManager(parameter_space)

############################################
##====SIMULATION AND COMPRESSION STAGE====##
############################################
print("Submitting simulation and compression jobs")
batch_manager.start_simulation_and_compression(force=force_rerun_simulations,
                                               clean_up=clean_up_simulation_files)
##########################
##====ANALYSIS STAGE====##
##########################
print("Submitting analysis jobs.")
batch_manager.start_analysis()

print("All jobs submitted.")
