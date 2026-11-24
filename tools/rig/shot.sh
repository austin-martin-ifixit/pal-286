#!/bin/bash
# A screenshot of the hidden screen: shot.sh NAME
ffmpeg -v error -y -f x11grab -video_size 800x600 -i :99 -frames:v 1 "/tmp/rig/$1.png"
