#!/bin/bash

# Script to run and test on my MacBook development system

# You need to activate flask311 virtual environment first
# conda activate flask311
# eval "$(conda shell.bash hook)"
# conda activate flask311

# RUN_ON_HOST:USING_PORT forms the URL where JavaScript posts are directed
# export RUN_ON_HOST="svpserver5.ddns.net"
export RUN_ON_HOST="localhost"
export USING_PORT="8080"

# mSec interval between updates to player browsers
export MINGO_UPDATE_INTERVAL="10000"

export MINGO_DEBUG_MODE="True"

# Execute the code!
python mingo_web.py
