import argparse
import datetime
import h5py
import hiisi
import numpy as np
import math
import json
import matplotlib.pyplot as plt
import os
import sys
from pathlib import Path
import logging

import pandas as pd

import utils


def read_config(config_file):
    """Read parameters from config file.

    Keyword arguments:
    config_file -- json file containing input parameters

    Return:
    coef -- dictionary containing coefficients
    input_conf -- dictionary containing input parameters
    output_conf -- dictionary containing output parameters

    """

    with open(config_file, "r") as jsonfile:
        data = json.load(jsonfile)

    input_conf = data["input"]
    output_conf = data["output"]

    return input_conf, output_conf


def timerange(first_timestamp, last_timestamp, timeres_mins, reverse=False):
    """Generator function for getting a list of timestamps

    Keyword arguments:
    first_timestamp -- First timestamp on list
    last_timestamp -- Last timestamp on list
    timeres_mins -- Minutes between timestamps
    reverse -- if True, list timestamps from last to first

    Yield:
    list of timestamps

    """
    for n in range(int((last_timestamp - first_timestamp).total_seconds() / 60 / timeres_mins) + 1):
        if not reverse:
            yield (first_timestamp + datetime.timedelta(minutes=n * timeres_mins)).strftime("%Y%m%d%H%M")
        else:
            yield (last_timestamp - datetime.timedelta(minutes=n * timeres_mins)).strftime("%Y%m%d%H%M")


def main():

    # Read config
    config_file = f"/config/{options.config}.json"
    input_conf, output_conf = read_config(config_file)

    # Calculate first timestamp
    last_timestamp = options.timestamp
    formatted_last_timestamp = datetime.datetime.strptime(last_timestamp, "%Y%m%d%H%M")
    timeres = output_conf["timeres"]
    if timeres == "cumulative-from-midnight":
        formatted_first_timestamp = formatted_last_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    elif timeres == "cumulative-from-hour-start":
        formatted_first_timestamp = formatted_last_timestamp.replace(minute=0, second=0, microsecond=0)
    else:
        mins_between = timeres - input_conf["timeres"]
        formatted_first_timestamp = formatted_last_timestamp - datetime.timedelta(minutes=mins_between)
    first_timestamp = formatted_first_timestamp.strftime("%Y%m%d%H%M")

    print(f"first_timestamp={first_timestamp}, last_timestamp={last_timestamp}")

    allow_n_missing_timesteps = input_conf.get("allow_n_missing_timesteps", 3)
    allow_n_missing_timesteps_consecutive = input_conf.get("allow_n_missing_timesteps_consecutive", 2)

    read_timesteps = pd.date_range(start=first_timestamp, end=last_timestamp, freq=f"{input_conf['timeres']}T")
    file_df = pd.DataFrame(index=np.arange(read_timesteps.size), columns=["timestep", "filename", "exists"])
    file_df["timestep"] = read_timesteps.values
    file_df["filename"] = file_df["timestep"].map(
        lambda ts: Path(
            input_conf["dir"].format(year=ts.strftime("%Y"), month=ts.strftime("%m"), day=ts.strftime("%d"), FMI_RUN_ENV=os.getenv("FMI_RUN_ENV", "unset"))
        )
        / input_conf["filename"].format(
            timestamp=ts.strftime("%Y%m%d%H%M"), timeres=f'{input_conf["timeres"]:03}', config=options.config
        )
    )
    file_df["exists"] = file_df["filename"].map(lambda f: f.exists())
    file_df.loc[~file_df["exists"], "filename"] = np.nan

    # Find missing intervals
    missing_intervals = file_df.filename.notna().cumsum()[file_df.filename.isna()]
    # lengths of consecutive missing intervals,
    lengths_consecutive_missing = missing_intervals.groupby(missing_intervals).agg(len)
    # the index of this is the is the cumsum value so we need to set the index to the original index
    lengths_consecutive_missing.index = missing_intervals.index[
        missing_intervals.searchsorted(lengths_consecutive_missing.index.values)
    ]
    total_missing_timesteps = lengths_consecutive_missing.sum()

    logging.warning(
        f"Missing timesteps: {[ts.strftime('%Y-%m-%d %H:%M') for ts in file_df[file_df['filename'].isna()].timestep]}"
    )
    logging.warning(f"Total missing timesteps: {total_missing_timesteps}")
    if total_missing_timesteps > allow_n_missing_timesteps:
        logging.critical(
            f"Too many missing files ({total_missing_timesteps}) when {allow_n_missing_timesteps} allowed. Exiting."
        )
        sys.exit(1)

    if lengths_consecutive_missing.max() > allow_n_missing_timesteps_consecutive:
        logging.critical(
            f"Too many consecutive missing files ({lengths_consecutive_missing.max()}) when {allow_n_missing_timesteps_consecutive} allowed. Exiting."
        )
        sys.exit(1)

    # Pad missing timesteps with closest existing timestep
    for missing_start_idx, missing_length in lengths_consecutive_missing.items():
        if missing_start_idx == 0:
            last_valid_path = None
            last_valid_timestep = None
        else:
            last_valid_path = file_df.iloc[missing_start_idx - 1]["filename"]
            last_valid_timestep = file_df.iloc[missing_start_idx - 1].timestep
        if missing_start_idx + missing_length == file_df.index.size:  # missing interval goes to end
            next_valid_path = None
            next_valid_timestep = None
        else:
            next_valid_path = file_df.iloc[missing_start_idx + missing_length]["filename"]
            next_valid_timestep = file_df.iloc[missing_start_idx + missing_length].timestep

        for i in range(missing_length):
            missing_idx = missing_start_idx + i
            # Check if missing timestep is closer to previous or next timestep
            try:
                timediff_last = (file_df.iloc[missing_idx].timestep - last_valid_timestep).total_seconds()
            except TypeError:
                timediff_last = np.inf
            try:
                timediff_next = (next_valid_timestep - file_df.iloc[missing_idx].timestep).total_seconds()
            except TypeError:
                timediff_next = np.inf
            closest_path = last_valid_path if timediff_last <= timediff_next else next_valid_path
            # Put closest path to missing timestep
            file_df.at[missing_idx, "filename"] = closest_path

    files = file_df["filename"].values

    acc_rate = None
    for filename in files:
        # Read the file
        image_array, quantity, infile_timestamp, gain, offset, nodata, undetect = utils.read_hdf5(filename)

        nodata_mask = image_array == nodata
        undetect_mask = image_array == undetect

        # Convert to physical values
        image_array = image_array * gain + offset

        # Change nodata and undetect to zero and np.nan before sum
        image_array[nodata_mask] = np.nan
        image_array[undetect_mask] = 0

        if acc_rate is None:
            # Init arrays
            acc_rate = image_array
            file_dict_accum = utils.init_filedict_accumulation(filename)

        else:
            # Calculate sum
            acc_rate = np.where(np.isnan(acc_rate), image_array, acc_rate + np.nan_to_num(image_array))

    # Write to file
    nodata_mask = ~np.isfinite(acc_rate)
    undetect_mask = acc_rate == 0
    acc_rate = utils.convert_dtype(acc_rate, output_conf, nodata_mask, undetect_mask)

    # Write to file
    outfile = Path(
        output_conf["dir"].format(
            year=last_timestamp[0:4], month=last_timestamp[4:6], day=last_timestamp[6:8], config=options.config, FMI_RUN_ENV=os.getenv("FMI_RUN_ENV", "unset")
        )
    ) / Path(output_conf["filename"].format(
        timestamp=last_timestamp,
        timeres=(
            f'{int((formatted_last_timestamp - formatted_first_timestamp).total_seconds() / 60):04}'
            if timeres == "cumulative-from-midnight"
            else f'{int((formatted_last_timestamp - formatted_first_timestamp).total_seconds() / 60):03}'
            if timeres == "cumulative-from-hour-start"
            else f'{timeres:03}'
        )
    ))
    data_first_timestamp = (formatted_first_timestamp - (datetime.timedelta(minutes=input_conf["timeres"]))).strftime(
        "%Y%m%d%H%M%S"
    )
    startdate = data_first_timestamp[0:8]
    starttime = data_first_timestamp[8:14]
    # enddate = last_timestamp[0:8]
    # endtime = last_timestamp[8:14]
    enddate = formatted_last_timestamp.strftime("%Y%m%d")
    endtime = formatted_last_timestamp.strftime("%H%M%S")
    date = enddate
    time = endtime

    utils.write_accumulated_h5(
        outfile, acc_rate, file_dict_accum, date, time, startdate, starttime, enddate, endtime, output_conf
    )


if __name__ == "__main__":
    # Parse commandline arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--timestamp", type=str, default="202201170700", help="Input timestamp")
    parser.add_argument("--config", type=str, default="hulehenri_composite", help="Config file to use.")

    options = parser.parse_args()
    args = vars(options)
    main()
