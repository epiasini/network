#!/bin/bash -l
#$ -S /bin/bash
#$ -cwd
#$ -o $HOME/log/
#$ -e $HOME/log/
#$ -l mem=3G
#$ -l h_rt=7:45:00
#$ -P gclayer13
#$ -l tmpfs=15G

# "jobscripts" are things that should be passed to qsub.

args_list=$@

echo $args_list

hostname
date
echo "Working in local scratch space $TMPDIR"
/usr/bin/time python compress.py $args_list
