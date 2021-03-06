import random
import xml.etree.ElementTree as ET

from java.util import ArrayList

from ucl.physiol.neuroconstruct.simulation import RandomSpikeTrainSettings, RandomSpikeTrainVariableSettings
from ucl.physiol.neuroconstruct.project.cellchoice import FixedNumberCells
from ucl.physiol.neuroconstruct.utils import NumberGenerator

def generate_nC_network(point, project_manager, project, sim_config):
    """
    This should be used instead than pm.doGenerate(sim_config_name,
    nC_seed) to build the general structure of the network
    """
    # delete all existing cells
    for cell_group in ['MFs', 'GrCs']:
        adapter = project.cellGroupsInfo.getCellPackingAdapter(cell_group)
        adapter.reset()
    project.generatedCellPositions.reset()    
    # set cell positions according to network graph
    for node in point.network_graph.nodes():
        cell, group_name = point.nC_cell_index_from_graph_node(node)
        project.generatedCellPositions.addPosition(group_name,
                                                   cell,
                                                   point.network_graph.node[node]['x'],
                                                   point.network_graph.node[node]['y'],
                                                   point.network_graph.node[node]['z'])
    # delete all existing generated connections
    project.generatedNetworkConnections.reset()
    # generate connections according to the network graph
    for mf in point.graph_mf_nodes:
        for gr in point.network_graph.neighbors(mf):
            for syn_type in ['RothmanMFToGrCAMPA', 'RothmanMFToGrCNMDA']:
                conn_name = 'MFs_to_GrCs_' + syn_type[-4:]
                project.generatedNetworkConnections.addSynapticConnection(conn_name, point.nC_cell_index_from_graph_node(mf)[0], point.nC_cell_index_from_graph_node(gr)[0])

    #export_to_neuroml(point, project, sim_config)

def generate_nC_saves(point, project):
    """
    This should be used instead than pm.doGenerate(sim_config_name,
    nC_seed) to set up the saves for the simulation.
    """
    # delete all existing plots and saves
    project.generatedPlotSaves.reset()
    
    # include saves for MFs and GrCs
    for sim_plot_name in ["MF_spikes", "GrC_spikes"]:
        all_cells_in_group = True
        all_segments = False
        sim_plot = project.simPlotInfo.getSimPlot(sim_plot_name)
        cell_nums_to_plot_list = [int(x) for x in range(project.generatedCellPositions.getNumberInCellGroup(sim_plot.getCellGroup()))]
        cell_nums_to_plot = ArrayList(cell_nums_to_plot_list)
        seg_ids_to_plot = ArrayList([int(sim_plot.getSegmentId())])
        project.generatedPlotSaves.addPlotSaveDetails(sim_plot.getPlotReference(),
                                                      sim_plot,
                                                      cell_nums_to_plot,
                                                      seg_ids_to_plot,
                                                      all_cells_in_group,
                                                      all_segments)

def generate_nC_stimuli(point, project, sim_config, stim_pattern):
    """
    This should be used instead than pm.doGenerate(sim_config_name,
    nC_seed) to set up a specific stimulation pattern.

    """
    # delete all existing stimuli
    project.generatedElecInputs.reset()
    project.elecInputInfo.deleteAllStims()
    sim_config.setInputs(ArrayList())
    # generate set firing rates for stimuli according to the current
    # stimulation pattern
    for mf in range(point.n_mf):
        if mf in stim_pattern:
            if point.stim_rate_sigma > 0:
                rate = max(0.1, random.gauss(point.stim_rate_mu, point.stim_rate_sigma))
            else:
                rate = point.stim_rate_mu
        else:
            if point.noise_rate_sigma > 0:
                rate = max(0.1, random.gauss(point.noise_rate_mu, point.noise_rate_sigma))
            else:
                rate = point.noise_rate_mu

        rate_in_khz = rate/1000.
        if not point.modulation_frequency:
            stim_type = 'RandomSpikeTrain'
            stim = RandomSpikeTrainSettings('MF_stim_'+str(mf), 'MFs', FixedNumberCells(0), 0, NumberGenerator(rate_in_khz), 'FastSynInput')
        else:
            stim_type = 'RandomSpikeTrainVariable'
            modulation_frequency_in_khz = point.modulation_frequency/1000.
            rate_string = '{} * (1 + 0.5 * sin(2 * 3.14159265 * t * {}))'.format(rate_in_khz, modulation_frequency_in_khz)
            stim = RandomSpikeTrainVariableSettings('MF_stim_'+str(mf), 'MFs', FixedNumberCells(0), 0, rate_string, 'FastSynInput', NumberGenerator(0), NumberGenerator(point.sim_duration))
        project.elecInputInfo.addStim(stim)
        sim_config.addInput(stim.getReference())
        project.generatedElecInputs.addSingleInput(stim.getReference(), stim_type, 'MFs', mf, 0, 0, None)

def set_tonic_GABA(project_dir, conductance_in_nS, reversal_potential=-79.1):
    """
    Modify the IaF_GrC_no_tonic_GABA.nml file in the working copy of
    the nC project to change the level of tonic GABA from what is
    originally set in the model.

    """
    ET.register_namespace('', 'http://www.neuroml.org/schema/neuroml2')
    filename = project_dir + "/cellMechanisms/IaF_GrC_no_tonic_GABA/IaF_GrC_no_tonic_GABA.nml"
    tree = ET.parse(filename)
    root = tree.getroot()
    cell = root.find("{http://www.neuroml.org/schema/neuroml2}iafRefCell")
    old_conductance = float(cell.get('leakConductance').rstrip('nS'))
    old_reversal_potential = float(cell.get('leakReversal').rstrip('mV'))
    new_conductance = old_conductance + conductance_in_nS
    new_reversal_potential = (old_conductance * old_reversal_potential + conductance_in_nS * reversal_potential)/new_conductance
    cell.set('leakConductance', '{}nS'.format(new_conductance))
    cell.set('leakReversal', '{}mV'.format(new_reversal_potential))
    tree.write(filename, encoding="UTF-8", xml_declaration=True)

def scale_synaptic_conductance(project_dir, component_name, scaling_factor, attributes_to_scale, units='nS'):
    ET.register_namespace('', 'http://www.neuroml.org/schema/neuroml2')
    filename = project_dir + "/cellMechanisms/{0}/{0}.nml".format(component_name)
    tree = ET.parse(filename)
    root = tree.getroot()
    synapse = root.findall(".//*[@id='{}']".format(component_name))[0]
    for attribute in attributes_to_scale:
        old_conductance = float(synapse.get(attribute).rstrip(units))
        new_conductance = old_conductance * scaling_factor
        synapse.set(attribute, '{}{}'.format(new_conductance, units))
    tree.write(filename, encoding="UTF-8", xml_declaration=True)


def scale_excitatory_conductances(project_dir, scaling_factor):
    """
    Modify the RothmanMFToGrCAMPA.nml and RothmanMFToGrCNMDA.nml files
    in the working copy of of the nC project to scale the total amount
    of excitatory conductance.

    """
    # scale AMPA
    scale_synaptic_conductance(project_dir=project_dir,
                               component_name='RothmanMFToGrCAMPA',
                               scaling_factor=scaling_factor,
                               attributes_to_scale=['directAmp1',
                                                    'directAmp2',
                                                    'spilloverAmp1',
                                                    'spilloverAmp2',
                                                    'spilloverAmp3'])
    # scale NMDA
    scale_synaptic_conductance(project_dir=project_dir,
                               component_name='RothmanMFToGrCNMDA',
                               scaling_factor=scaling_factor,
                               attributes_to_scale=['directAmp1',
                                                    'directAmp2'])

def export_to_neuroml(project, sim_config, out_path):
    # export to NeuroML (debug feature)
    from java.io import File
    from ucl.physiol.neuroconstruct.neuroml import NeuroMLFileManager, NeuroMLConstants, LemsConstants
    from ucl.physiol.neuroconstruct.cell.compartmentalisation import CompartmentalisationManager
    from ucl.physiol.neuroconstruct.utils.units import UnitConverter
    
    neuroml_version = NeuroMLConstants.NeuroMLVersion.getLatestVersion()
    lems_option = LemsConstants.LemsOption.NONE
    mc = CompartmentalisationManager.getOrigMorphCompartmentalisation()
    units = UnitConverter.getUnitSystemDescription(UnitConverter.GENESIS_PHYSIOLOGICAL_UNITS);

    print('Exporting network in NeuroML2 format in ' + out_path)
    project.neuromlFileManager.reset()
    project.neuromlFileManager.generateNeuroMLFiles(sim_config, neuroml_version, lems_option, mc, 1234, False, False, File(out_path), units, False)
        
