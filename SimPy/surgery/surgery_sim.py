"""
Object oriented medical operation model
Patients arrive and are registered, then move to triage
after triage they go either to ed or acu service and then exit
"""

from itertools import count
from collections import namedtuple
import random
import sqlite3

from simpy import Resource, Environment
import pandas as pd

from simulation_config import SimulationConfig

Team = namedtuple("Team", "pool service_time")
DataPoint = namedtuple("DataPoint", "timestamp q_len")


class MonitoredResource(Resource):
    """
    Keep track of the number of waiting calls (queue length) at each
    request/release which are implicitly called by a context manager (with ... as:)

    Copies the technique described in the SimPy docs - to provide a dynamic visualization the
    queue lengths, # resources occupied etc could be injected into a database, then use visualization
    software to display.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats = []

    # implicitly called at entry of "with" block
    def request(self, *args, **kwargs):
        self.stats.append(DataPoint(self._env.now, len(self.queue)))
        return super().request(*args, **kwargs)

    # implicitly called at exit of "with" block
    def release(self, *args, **kwargs):
        self.stats.append(DataPoint(self._env.now, len(self.queue)))
        return super().release(*args, **kwargs)


# pylint: disable=too-few-public-methods
class Patient:
    """
    Patient: the entity that goes through the system
    """

    def __init__(self, patient_id, p_ed):
        self.id = patient_id
        self.timestamps = {}
        self.is_for_ed = random.uniform(0, 1) < p_ed


class SurgerySimulation:
    """
    Executes the process steps of a single surgery simulation
    """

    def __init__(self, run_id, config):
        self.run_id = run_id
        self.config = config
        self.patients = []
        self.env = Environment()

        # Establish staffing levels for each team/service as
        # SimPy Resources (monitoring queue lengths)
        receptionist_pool = MonitoredResource(
            self.env, capacity=self.config.n_receptionists
        )
        nurse_pool = MonitoredResource(self.env, capacity=self.config.n_nurses)
        ed_doctor_pool = MonitoredResource(self.env, capacity=self.config.n_ed_doctors)
        acu_doctor_pool = MonitoredResource(
            self.env, capacity=self.config.n_acu_doctors
        )

        # Save the team resources and mean service times as a dictionary
        # of named tuples – keyed on the name of the team
        self.teams = {
            "registration": Team(receptionist_pool, self.config.reception_service_mean),
            "triage": Team(nurse_pool, self.config.triage_service_mean),
            "ed": Team(ed_doctor_pool, self.config.ed_service_mean),
            "acu": Team(acu_doctor_pool, self.config.acu_service_mean),
        }

    @property
    def is_warming_up(self):
        return self.env.now < self.config.warm_up_time

    def generate_patients(self):
        for patient_id in count():
            patient = Patient(patient_id, self.config.patient_p_ed)
            if not self.is_warming_up:
                # keep track of our patient
                self.patients.append(patient)

            # put the patient in the system
            self.env.process(self.process_patient(patient))

            # wait until next person to walks in
            yield self.env.timeout(
                random.expovariate(1 / self.config.patient_inter_arrival_time)
            )

    def process_patient(self, patient):
        """Send the patient through the sequence of steps in the clinic"""

        treatment = "ed" if patient.is_for_ed else "acu"
        process_steps = ["registration", "triage", treatment]
        for step in process_steps:
            yield from self.do_service(patient, step)
        patient.timestamps["exit"] = self.env.now

    def do_service(self, patient, service_name):
        """
        Generic service call:
        Waits for the service resource to be available
        Then waits for the service to complete
        The patient logs the time at each stage: entry, start, exit
        """

        patient.timestamps[service_name + "_entry"] = self.env.now
        resource = self.teams[service_name].pool
        service_time = self.teams[service_name].service_time
        with resource.request() as request:
            yield request
            patient.timestamps[service_name + "_start"] = self.env.now
            yield self.env.timeout(random.expovariate(1 / service_time))
            patient.timestamps[service_name + "_exit"] = self.env.now

    def run(self):
        total_run_time = self.config.warm_up_time + self.config.simulation_time
        self.env.process(self.generate_patients())
        self.env.run(until=total_run_time)


class SimulationDriver:
    """
    Sets-up and drives the whole simulation.
    Saves the stats to sqlite db at the end of each run
    """

    def __init__(self, config_filename, drop_tables=True):
        self.config = SimulationConfig(config_filename)
        self.init_db(drop_tables)
        self.simulation = None

    def init_db(self, drop_tables):
        self.db = sqlite3.connect(self.config.db_filename)
        if drop_tables:
            cur = self.db.cursor()
            for table in [self.config.db_patients_table, self.config.db_queues_table]:
                sql = f"drop table if exists {table};"
                cur.execute(sql)
            cur.close()

    def save_stats(self):
        self.save_queue_lengths()
        self.save_patient_stats()

    def save_patient_stats(self):
        """Save the patient statistics to sqlite at the end of each run"""

        # create a list of stats for each patient in the run
        #
        # use dict.get() as some values may be None i.e. patients that didn't
        # make it the whole way through the system and because ed & acu are exclusive
        rows = [
            (
                self.simulation.run_id,
                p.id,
                p.is_for_ed,
                p.timestamps.get("registration_entry"),
                p.timestamps.get("registration_start"),
                p.timestamps.get("registration_exit"),
                p.timestamps.get("triage_entry"),
                p.timestamps.get("triage_start"),
                p.timestamps.get("triage_exit"),
                p.timestamps.get("ed_entry"),
                p.timestamps.get("ed_start"),
                p.timestamps.get("ed_exit"),
                p.timestamps.get("acu_entry"),
                p.timestamps.get("acu_start"),
                p.timestamps.get("acu_exit"),
                p.timestamps.get("exit"),
            )
            for p in self.simulation.patients
        ]

        # These columns MUST be in the same order as the above tuples
        columns = [
            "run_id",
            "patient_id",
            "is_for_ed",
            "registration_entry",
            "registration_start",
            "registration_exit",
            "triage_entry",
            "triage_start",
            "triage_exit",
            "ed_entry",
            "ed_start",
            "ed_exit",
            "acu_entry",
            "acu_start",
            "acu_exit",
            "exit",
        ]

        df = pd.DataFrame(data=rows, columns=columns)
        df.to_sql(
            self.config.db_patients_table,
            self.db,
            index=False,
            method="multi",
            if_exists="append",
        )
        self.db.commit()

    def save_queue_lengths(self):
        """Save the queue statistics to sqlite at the end of each run"""

        rows = []
        for service, team in self.simulation.teams.items():
            data = [
                {
                    "run_id": self.simulation.run_id,
                    "service": service,
                    "timestamp": d.timestamp,
                    "q_len": d.q_len,
                }
                for d in team.pool.stats
            ]
            rows += data
        df = pd.DataFrame(rows)
        df.to_sql(
            self.config.db_queues_table,
            self.db,
            index=False,
            method="multi",
            if_exists="append",
        )
        self.db.commit()

    def run_once(self, run_id):
        self.simulation = SurgerySimulation(run_id, self.config)
        self.simulation.run()
        self.save_stats()

    def run(self):
        try:
            for run_id in range(self.config.n_sims):
                self.run_once(run_id)
        finally:
            self.db.close()


def main(config_file):
    driver = SimulationDriver(config_file)
    driver.run()


CONFIG_FILE = "simulation.ini"

if __name__ == "__main__":
    main(CONFIG_FILE)
