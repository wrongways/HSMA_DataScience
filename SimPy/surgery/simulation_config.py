from configparser import ConfigParser
from pathlib import Path
import sys


class SimulationConfig:
	"""
		Reads the simulation config file and presents the values
		as easy-to-use attributes with the correct type
	"""

	def __init__(self, config_filename):
		config_path = Path(config_filename)
		if not (config_path.exists and config_path.is_file()):
			bel = '\07'
			sys.exit(f'File {config_path} does not exist{bel}')

		config = ConfigParser()
		config.read(config_path)
		self.config = {section.lower(): dict(config[section]) for section in config.sections()}

	@property
	def patient_config(self):
		return self.config['patient']
	@property
	def reception_config(self):
		return self.config['reception']
	@property
	def nurse_config(self):
		return self.config['nurse']
	@property
	def doctor_config(self):
		return self.config['doctor']
	@property
	def db_config(self):
		return self.config['db']
	@property
	def db_filename(self):
		return self.db_config['filename']
	@property
	def db_patients_table(self):
		return self.db_config['patients_table']
	@property
	def db_queues_table(self):
		return self.db_config['queue_length_table']
	@property
	def simulation_config(self):
		return self.config['simulation']
	@property
	def warm_up_time(self):
		return int(self.simulation_config['warm_up'])
	@property
	def simulation_time(self):
		return int(self.simulation_config['sim_duration'])
	@property
	def n_sims(self):
		return int(self.simulation_config['n_sims'])
	@property
	def plot_config(self):
		return dict(self.config['plot'])
	@property
	def plot_time_bin_size(self):
		return int(self.plot_config['bin_size'])
	@property
	def patient_inter_arrival_time(self):
		return int(self.patient_config['inter_arrival_time'])
	@property
	def patient_p_ed(self):
		return float(self.patient_config['p_ed'])
	@property
	def n_receptionists(self):
		return int(self.reception_config['n_receptionists'])
	@property
	def n_nurses(self):
		return int(self.nurse_config['n_nurses'])
	@property
	def n_ed_doctors(self):
		return int(self.doctor_config['n_ed_doctors'])
	@property
	def n_acu_doctors(self):
		return int(self.doctor_config['n_acu_doctors'])
	@property
	def reception_service_mean(self):
		return int(self.reception_config['mean_reception_time'])
	@property
	def triage_service_mean(self):
		return int(self.nurse_config['mean_triage_time'])
	@property
	def ed_service_mean(self):
		return int(self.doctor_config['mean_ed_consult_time'])
	@property
	def acu_service_mean(self):
		return int(self.doctor_config['mean_acu_consult_time'])
