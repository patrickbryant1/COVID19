#!/usr/bin/env bash


EPIDATA=/home/patrick/COVID19.github.io/simulations/mobility/data/ecdc_20200521.csv
OUTDIR=/home/patrick/results/COVID19/R_estimates/
COUNTRIES=/home/patrick/COVID19.github.io/simulations/mobility_signal/estimate_R/countries.txt
time for i in {1..209}
  do
    COUNTRY=$(sed -nr $i'p' $COUNTRIES)
    echo $COUNTRY
    Rscript /home/patrick/COVID19.github.io/simulations/mobility_signal/estimate_R/model_R.R $EPIDATA $COUNTRY $OUTDIR
  done
