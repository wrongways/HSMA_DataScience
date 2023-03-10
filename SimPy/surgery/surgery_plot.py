import sqlite3
import sys
from pathlib import Path

import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt

from simulation_config import SimulationConfig

CONFIG_FILE = "simulation.ini"
IMG_FILES_ROOT = "simulation"

# Terminal escape sequences: Esc = 27 = 033 (octal: 3 * 8 + 3)
RED = "\033[31m"
GREEN = "\033[32m"
NORMAL = "\033[0m"
HIGHLIGHT = GREEN


class Plotter:
    def __init__(self, config_file):
        self.config = SimulationConfig(config_file)
        self.init_db()
        self.services = ["registration", "triage", "ed", "acu"]

    def init_db(self):
        self.db = sqlite3.connect(self.config.db_filename)

    def load_queues(self, bin_size):
        sql = f"select round(timestamp/{bin_size}) as hour, avg(q_len) as q_len, service  from {self.config.db_queues_table} where hour > {self.config.warm_up_time/bin_size} group by hour,service;"
        return pd.read_sql(sql, self.db)

    def load_patients(self, bin_size):
        """read the patients table into a dataframe

        The select does the heavy lifting so the dataframe is in a form ready to use

        The dataframe columns are: service, hour, wait_time
        This regular form allows us to use service as hue to the lineplot
        The wait times are are averaged across each run and for each bin_size eg 15'
        """

        dfs = []
        for service in self.services:
            sql = f"""select "{service}" as service, round(registration_entry/{bin_size}) as hour,
                avg({service}_start - {service}_entry) as wait_time
                from {self.config.db_patients_table}  group by hour;
                """
            dfs.append(pd.read_sql(sql, self.db))

        # concatenating dataframes is expensive, only do it once
        return pd.concat(dfs, ignore_index=True)

    def plot_queue_box(self, ax):
        queues_df = self.load_queues(bin_size=1)
        sns.boxplot(
            ax=ax, data=queues_df, x="service", y="q_len", order=self.services
        ).set(title="Queue lengths", ylabel="Number of waiting patitents")

    def plot_waits_box(self, ax):
        waits_df = self.load_patients(bin_size=1)
        waits_df.wait_time /= 60
        sns.boxplot(
            ax=ax, data=waits_df, x="service", y="wait_time", order=self.services
        ).set(title="Wait times", ylabel="Wait time (hours)")

    def plot_queues(self, ax):
        ax.set(title="Queue lengths", ylabel="Number of patients waiting for service")

        # load the data from SQLite DB into a Pandas dataframe
        queues_df = self.load_queues(bin_size=self.config.plot_time_bin_size)

        # Subtract the warm-up duration from timestamps, so plot starts at 0
        queues_df.hour -= self.config.warm_up_time / self.config.plot_time_bin_size

        # Scale the x-axis to hours rather than minutes
        queues_df.hour /= 60 / self.config.plot_time_bin_size

        # Draw the plot on the axis
        sns.lineplot(
            ax=ax,
            data=queues_df,
            x="hour",
            y="q_len",
            hue="service",
            hue_order=self.services,
        )

    def plot_waits(self, ax):
        ax.set(title="Waiting times", ylabel="Wait times (hours)")
        waits_df = self.load_patients(self.config.plot_time_bin_size)
        waits_df.hour -= self.config.warm_up_time / self.config.plot_time_bin_size
        waits_df.hour /= 60 / self.config.plot_time_bin_size
        waits_df.wait_time /= 60  # turn minutes into hours
        sns.lineplot(
            ax=ax,
            data=waits_df,
            x="hour",
            y="wait_time",
            hue="service",
            hue_order=self.services,
        )

        # Report the quantile
        quantile = 0.95
        for service in self.services:
            service_df = waits_df[waits_df.service == service]
            text = f"{service} wait {quantile * 100:.0f}th percentile: "
            print(f"{text:>40}{service_df.wait_time.quantile(quantile):5.2f} hours")
        print()

    def plot_time_series(self):
        fig, ax = plt.subplots(
            2, 1, constrained_layout=False, figsize=(20, 15), sharex=True
        )
        fig.suptitle("Simulation results")
        self.plot_queues(ax[0])
        self.plot_waits(ax[1])
        plt.savefig(f"{IMG_FILES_ROOT}_results.png", dpi=300)

    def plot_variability(self):
        fig, ax = plt.subplots(
            2, 1, constrained_layout=False, figsize=(20, 15), sharex=False
        )
        fig.suptitle("Simulation results")
        self.plot_queue_box(ax[0])
        self.plot_waits_box(ax[1])
        plt.savefig(f"{IMG_FILES_ROOT}_variablility.png", dpi=300)

    def plot_results(self):
        try:
            self.plot_time_series()
            self.plot_variability()
        finally:
            self.db.close()


def main():
    save_filename = IMG_FILES_ROOT
    if len(sys.argv) > 1:
        save_filename = sys.argv[1]
        for ext in ["results", "variability"]:
            filename = f"{save_filename}_{ext}.png"
            imgfile = Path(filename)
            if imgfile.exists():
                yn = input(f"{imgfile} already exists. Overwrite [Yn]: ")
                if yn and yn.lower()[0] != "y":
                    sys.exit(0)

    plotter = Plotter(CONFIG_FILE)
    plotter.plot_results()
    print(
        f" 📈 Plots are in {HIGHLIGHT}{save_filename}_results.png{NORMAL} and {HIGHLIGHT}{save_filename}_variability.png{NORMAL}. Enjoy..."
    )


if __name__ == "__main__":
    main()
