import argparse
import datetime
import h5py
import hiisi
import numpy as np
import math
import json
import matplotlib.pyplot as plt

import utils

def read_config(config_file):
    """ Read parameters from config file.                                                          
                                                                                                   
    Keyword arguments:                                                                             
    config_file -- json file containing input parameters                                           
                                                                                                   
    Return:                                                                                        
    coef -- dictionary containing coefficients                                                     
    input_conf -- dictionary containing input parameters                                           
    output_conf -- dictionary containing output parameters                                         
                                                                                                   
    """

    with open(config_file, "r") as jsonfile:
        data = json.load(jsonfile)

    input_conf = data['input']
    output_conf = data['output']

    return input_conf, output_conf


def timerange(first_timestamp, last_timestamp, timeres_mins, reverse = False):
    """ Generator function for getting a list of timestamps                                         
                                                                 
    Keyword arguments:                                                                            
    first_timestamp -- First timestamp on list                                            
    last_timestamp -- Last timestamp on list                                                 
    timeres_mins -- Minutes between timestamps                        
    reverse -- if True, list timestamps from last to first                                                   
                                                                                                
    Yield:                                                                                                 
    list of timestamps                                                                                       
                                     
    """
    for n in range(int((last_timestamp - first_timestamp).total_seconds()/60/timeres_mins)+1):
        if not reverse:
            yield (first_timestamp + datetime.timedelta(minutes = n*timeres_mins)).strftime("%Y%m%d%H%M")
        else:
            yield (last_timestamp - datetime.timedelta(minutes = n*timeres_mins)).strftime("%Y%m%d%H%M")


def main():

    # Read config
    config_file = f'/config/{options.config}.json'
    input_conf, output_conf = read_config(config_file)

    # Calculate first timestamp
    last_timestamp = options.timestamp
    formatted_last_timestamp = datetime.datetime.strptime(last_timestamp,'%Y%m%d%H%M')
    mins_between = output_conf['timeres'] - input_conf['timeres']
    formatted_first_timestamp = formatted_last_timestamp - (datetime.timedelta(minutes = mins_between))
    first_timestamp = formatted_first_timestamp.strftime('%Y%m%d%H%M')
    
    print("first_timestamp= ", first_timestamp)
    print("last_timestamp= ", last_timestamp)

    for timestamp in timerange(formatted_first_timestamp, formatted_last_timestamp, input_conf['timeres'], reverse = False):
        
        # Read file
        filename = f"{input_conf['dir'].format(year=timestamp[0:4], month=timestamp[4:6], day=timestamp[6:8])}" + "/" + input_conf['filename'].format(timestamp=timestamp, timeres = f'{input_conf["timeres"]:03}', config=options.config)
        image_array, quantity, infile_timestamp, gain, offset, nodata, undetect = utils.read_hdf5(filename)
        nodata_mask = (image_array == nodata)
        undetect_mask = (image_array == undetect)

        # Convert to physical values
        image_array = image_array * gain + offset
        
        # Change nodata and undetect to zero and np.nan before sum
        image_array[nodata_mask] = np.nan
        image_array[undetect_mask] = 0
        
        if timestamp == first_timestamp:
            # Init arrays
            acc_rate = image_array
            file_dict_accum = utils.init_filedict_accumulation(filename)
            
        else:
            # Calculate sum
            acc_rate = np.where(np.isnan(acc_rate), image_array, acc_rate + np.nan_to_num(image_array))            

    # Write to file
    nodata_mask = ~np.isfinite(acc_rate)
    undetect_mask = (acc_rate == 0)
    acc_rate = utils.convert_dtype(acc_rate, output_conf, nodata_mask, undetect_mask)

    #Write to file                                                                                                                          
    outfile = output_conf['dir'] + '/' + output_conf['filename'].format(timestamp = last_timestamp, timeres = f'{output_conf["timeres"]:03}') 
    data_first_timestamp = (formatted_first_timestamp - (datetime.timedelta(minutes = input_conf['timeres']))).strftime('%Y%m%d%H%M')
    startdate = data_first_timestamp[0:8]
    starttime = data_first_timestamp[8:14]
    enddate = last_timestamp[0:8]
    endtime = last_timestamp[8:14]
    date = enddate
    time = endtime

    utils.write_accumulated_h5(outfile, acc_rate, file_dict_accum, date, time, startdate, starttime, enddate, endtime, output_conf)
   

if __name__ == '__main__':
    #Parse commandline arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--timestamp',
                        type = str,
                        default = '202201170700',
                        help = 'Input timestamp')
    parser.add_argument('--config',
                        type = str,
                        default = 'hulehenri_composite',
                        help = 'Config file to use.')
    
    options = parser.parse_args()
    args = vars(options)
    main()
