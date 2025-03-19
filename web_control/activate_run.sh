#!/bin/bash

# Use the flask311 conda environment and run the program passed as an argument

# invoke dev_script.sh on MacBook as follows
# ./activate_run.sh dev_script.sh


conda run -n flask311 --live-stream ./$1
