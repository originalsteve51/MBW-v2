#!/bin/zsh

# Necessary to first run 'conda activate spotify_3.9'

# The Spotipy library requires the following information. This can be passed directly in the 
# program code (I think) but it should be isolated from source code by scripting it as
# shell environment variables.
export SPOTIPY_CLIENT_ID="2f9b6f9f32084d538aa69e74845a759a"
export SPOTIPY_CLIENT_SECRET="723dd34248ee4320b39f79feb23aacdc"
export SPOTIPY_REDIRECT_URI="http://127.0.0.1:8080"

# For web control, need the url where it is running
# export WEB_CONTROLLER_URL="http://localhost:8080"
export WEB_CONTROLLER_URL="http://svpserver5.ddns.net:8080"
# export WEB_CONTROLLER_URL="http://192.168.1.162:8080"

python mingo.py
