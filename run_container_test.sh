#!/bin/bash

# Build
#docker build --no-cache -t calc_accr_sum .

CONFIG=${CONFIG:-hulehenri_composite}

INPATH=/tutka/data/dev/cache/radar/fmippn/hulehenri/accrate_composites
LATEST_TIMESTAMP=`ls -t $INPATH | head -n1 | awk -F "_" '{print $1}'` #| awk -F "+" '{print $1}'`
TIMESTAMP=${TIMESTAMP:-${LATEST_TIMESTAMP}}

echo "latest timestamp:" $TIMESTAMP

OUTPATH=${OUTPATH:-/tutka/data/dev/cache/radar/fmippn/hulehenri/accrate}
LOGPATH=${LOGPATH:-/tutka/data/dev/cache/log/fmippn/hulehenri}

echo INPATH: $INPATH
echo OUTPATH: $OUTPATH
echo LOGPATH: $LOGPATH

#Mkdirs if log and outpaths have been cleaned                              
mkdir -p $OUTPATH
mkdir -p $LOGPATH

# Run
docker run \
       --env "timestamp=$TIMESTAMP" \
       --env "config=$CONFIG" \
       --mount type=bind,source=/tutka/data/dev/cache/radar/fmippn/hulehenri,target=/tutka/data/dev/cache/radar/fmippn/hulehenri \
       --mount type=bind,source=$LOGPATH,target=$LOGPATH \
       --mount type=bind,source="$(pwd)"/config,target=/config \
       --mount type=bind,source="$(pwd)"/calc_sum.py,target=/calc_sum.py \
       calc_accr_sum:latest
