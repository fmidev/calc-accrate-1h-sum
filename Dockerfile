FROM python:3.8

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir argparse datetime \
    numpy matplotlib h5py \
    git+https://github.com/fmidev/hiisi.git@f9063f70bdca5749b2fe71264bf975dbdfa24f77

# Workdir and input/output/log dir
WORKDIR .
RUN mkdir input output log
COPY . /

# Run
ENV config hulehenri
ENV timestamp 202301010000
ENTRYPOINT python calc_sum.py --config=$config --timestamp=$timestamp
