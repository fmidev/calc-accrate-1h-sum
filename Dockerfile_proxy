FROM python:3.8

ENV http_proxy 'http://wwwcache.fmi.fi:8080'
ENV https_proxy 'http://wwwcache.fmi.fi:8080'

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir argparse datetime \
    	numpy matplotlib h5py \
	git+https://github.com/karjaljo/hiisi.git

# Workdir and input/output/log dir
WORKDIR .
RUN mkdir input output log
COPY . /

# Run
ENV config hulehenri
ENV timestamp 202301010000
ENTRYPOINT python calc_sum.py --config=$config --timestamp=$timestamp
