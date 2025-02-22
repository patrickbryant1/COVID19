#! /usr/bin/env python3
# -*- coding: utf-8 -*-


import argparse
import sys
import os
import glob
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from scipy.stats import gamma
import numpy as np
import seaborn as sns


import pdb



#Arguments for argparse module:
parser = argparse.ArgumentParser(description = '''Visuaize results from model using google mobility data and age distributions''')

parser.add_argument('--datadir', nargs=1, type= str, default=sys.stdin, help = 'Path to outdir.')
parser.add_argument('--countries', nargs=1, type= str, default=sys.stdin, help = 'Countries to model (csv).')
parser.add_argument('--subregions', nargs=1, type= str, default=sys.stdin, help = 'Subregions to model (csv).')
parser.add_argument('--epidemic_data', nargs=1, type= str, default=sys.stdin, help = 'Subregion epidemic data (csv).')
parser.add_argument('--days_to_simulate', nargs=1, type= int, default=sys.stdin, help = 'Number of days to simulate.')
parser.add_argument('--end_date', nargs=1, type= str, default=sys.stdin, help = 'Up to which date to include data.')
parser.add_argument('--short_dates', nargs=1, type= str, default=sys.stdin, help = 'Short date format for plotting (csv).')
parser.add_argument('--outdir', nargs=1, type= str, default=sys.stdin, help = 'Path to outdir.')

def se_transl(mobility_data, epidemic_data):
    '''Ensure the county names are the same across dfs
    '''
    translations={"Blekinge County":"Blekinge",
    "Dalarna County":"Dalarna",
    "Gavleborg County":"Gävleborg",
    "Gotland County":"Gotland",
    "Halland County":"Halland",
    "Jamtland County":"JämtlandHärjedalen",
    "Jämtland Härjedalen":"JämtlandHärjedalen",
    "Jonkoping County":"Jönköping",
    "Kalmar County":"Kalmar",
    "Kronoberg County":"Kronoberg",
    "Norrbotten County":"Norrbotten",
    "Örebro County":"Örebro",
    "Östergötland County":"Östergötland",
    "Skåne County":"Skåne",
    "Södermanland County":"Sörmland",
    "Stockholm County":"Stockholm",
    "Uppsala County":"Uppsala",
    "Varmland County":"Värmland",
    "Västerbotten County":"Västerbotten",
    "Västernorrland County":"Västernorrland",
    "Västmanland County":"Västmanland",
    "Västra Götaland County":"VästraGötaland",
    "Västra Götaland":"VästraGötaland"}

    mobility_data.replace(translations, inplace=True)
    epidemic_data.replace(translations, inplace=True)
    return mobility_data, epidemic_data

def read_and_format_data(datadir, countries, subregions, epidemic_data, days_to_simulate, covariate_names, end_date):
        '''Read in and format all data needed for the model
        '''

        #Get epidemic data
        #Convert to datetime
        epidemic_data['date'] = pd.to_datetime(epidemic_data['date'], format='%Y/%m/%d')
        #Select all data up to end_date
        epidemic_data = epidemic_data[epidemic_data['date']<=end_date]
        #Mobility data
        mobility_data = pd.read_csv(datadir+'Global_Mobility_Report.csv')
        #Convert to datetime
        mobility_data['date']=pd.to_datetime(mobility_data['date'], format='%Y/%m/%d')
        #Get per country
        mobility_data = mobility_data[mobility_data['country_region']==countries[0]]
        #Fix varying names
        mobility_data, epidemic_data = se_transl(mobility_data, epidemic_data)


        #Model data - to be used for plotting
        stan_data = {'dates_by_country':np.zeros((days_to_simulate,len(subregions)), dtype='datetime64[D]'),
                    'deaths_by_country':np.zeros((days_to_simulate,len(subregions))),
                    'cases_by_country':np.zeros((days_to_simulate,len(subregions))),
                    'days_by_country':np.zeros(len(subregions)),
                    'retail_and_recreation_percent_change_from_baseline':np.zeros((days_to_simulate,len(subregions))),
                    'grocery_and_pharmacy_percent_change_from_baseline':np.zeros((days_to_simulate,len(subregions))),
                    'transit_stations_percent_change_from_baseline':np.zeros((days_to_simulate,len(subregions))),
                    'workplaces_percent_change_from_baseline':np.zeros((days_to_simulate,len(subregions))),
                    'residential_percent_change_from_baseline':np.zeros((days_to_simulate,len(subregions))),
                    }


        #Get data by country
        for c in range(len(subregions)):
                subregion = subregions[c]
                #Get country epidemic data
                county_epidemic_data = epidemic_data[epidemic_data['country']==subregion.split('County')[0].strip()]
                #Sort on date
                county_epidemic_data = county_epidemic_data.sort_values(by='date')
                #Reset index
                county_epidemic_data = county_epidemic_data.reset_index()

                #Get all dates with at least 10 deaths
                cum_deaths = county_epidemic_data['new_deaths'].cumsum()
                death_index = cum_deaths[cum_deaths>=10].index[0]
                di30 = death_index-30
                #Get part of county_epidemic_data 30 days before day with at least 10 deaths
                county_epidemic_data = county_epidemic_data.loc[di30:]
                #Reset index
                county_epidemic_data = county_epidemic_data.reset_index()

                print(subregion, len(county_epidemic_data))
                #Check that foreacast is really a forecast
                N = len(county_epidemic_data)
                stan_data['days_by_country'][c]=N
                forecast = days_to_simulate - N
                if forecast <0: #If the number of predicted days are less than the number available
                    days_to_simulate = N
                    forecast = 0
                    print('Forecast error!')
                    pdb.set_trace()

                #Save dates
                stan_data['dates_by_country'][:N,c] = np.array(county_epidemic_data['date'], dtype='datetime64[D]')
                #Save deaths
                deaths = np.array(county_epidemic_data['new_deaths'])
                #deaths_7 = np.zeros(N)
                #deaths_7[0:7] = np.sum(deaths[0:7])/7
                #for i in range(7,N):
                #    deaths_7[i] = np.sum(deaths[i-6:i+1])/7
                stan_data['deaths_by_country'][:N,c] = deaths

                #Save cases
                stan_data['cases_by_country'][:N,c] = county_epidemic_data['new_confirmed_cases']

                #Covariates - assign the same shape as others (N2)
                #Mobility data from Google
                county_cov_data = mobility_data[mobility_data['sub_region_1']==subregion]
                #Get whole county - no county subregion
                county_cov_data =  county_cov_data[county_cov_data['sub_region_2'].isna()]
                #Get matching dates
                county_cov_data = county_cov_data[county_cov_data['date'].isin(county_epidemic_data['date'])]
                end_date = max(county_cov_data['date']) #Last date for mobility data

                for name in covariate_names:
                    county_epidemic_data.loc[county_epidemic_data.index,name] = 0 #Set all to 0
                    for d in range(len(county_epidemic_data)): #loop through all country data
                        row_d = county_epidemic_data.loc[d]
                        date_d = row_d['date'] #Extract date
                        try:
                            change_d = np.round(float(county_cov_data[county_cov_data['date']==date_d][name].values[0])/100, 2) #Match mobility change on date
                            if not np.isnan(change_d):
                                county_epidemic_data.loc[d,name] = change_d #Add to right date in country data
                        except:
                            continue #Date too far ahead


                    #Add the latest available mobility data to all remaining days (including the forecast days)
                    county_epidemic_data.loc[county_epidemic_data['date']>=end_date, name]=change_d
                    cov_i = np.zeros(days_to_simulate)
                    cov_7 = np.zeros(days_to_simulate)
                    cov_i[:N] = np.array(county_epidemic_data[name])
                    #Do a 7-day sliding window for smoothing
                    cov_7[0:7]=np.sum(cov_i[0:7])/7
                    for m in range(7,N):
                        cov_7[m]=np.sum(cov_i[m-6:m+1])/7

                    #Add covariate info to forecast
                    cov_7[N:days_to_simulate]=cov_7[N-1]

                    stan_data[name][:,c] = cov_7

        return stan_data

def visualize_results(outdir, countries, stan_data, days_to_simulate, short_dates):
    '''Visualize results
    '''
    #params = ['mu', 'alpha', 'kappa', 'y', 'phi', 'tau', 'convolution', 'prediction',
    #'E_deaths', 'Rt', 'lp0', 'lp1', 'convolution0', 'prediction0', 'E_deaths0', 'lp__']
    #lp0[i,m] = neg_binomial_2_log_lpmf(deaths[i,m] | E_deaths[i,m],phi);
    #lp1[i,m] = neg_binomial_2_log_lpmf(deaths[i,m] | E_deaths0[i,m],phi);
    #'prediction0', 'E_deaths0' = w/o mobility changes

    #Read in data
    #For models fit using MCMC, also included in the summary are the
    #Monte Carlo standard error (se_mean), the effective sample size (n_eff),
    #and the R-hat statistic (Rhat).
    summary = pd.read_csv(outdir+'summary.csv')
    #cases = np.load(outdir+'prediction.npy', allow_pickle=True)
    #deaths = np.load(outdir+'E_deaths.npy', allow_pickle=True)
    #Rt =  np.load(outdir+'Rt.npy', allow_pickle=True)
    alphas = np.load(outdir+'alpha.npy', allow_pickle=True)
    phi = np.load(outdir+'phi.npy', allow_pickle=True)
    days = np.arange(0,days_to_simulate) #Days to simulate
    #Plot rhat
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(summary['Rhat'])
    ax.set_ylabel('Count')
    ax.set_xlabel("Rhat")
    fig.savefig(outdir+'plots/rhat.png', format='png', dpi=300)
    plt.close()

    #Plot values from each iteration as r function mcmc_parcoord
    mcmc_parcoord(np.concatenate([alphas,np.expand_dims(phi,axis=1)], axis=1), covariate_names+['phi'], outdir)

    #Plot alpha (Rt = R0*-exp(sum{mob_change*alpha1-6}))
    fig, ax = plt.subplots(figsize=(9/2.54, 9/2.54))
    alpha_colors = {0:'tab:red',1:'tab:purple',2:'tab:pink', 3:'tab:olive', 4:'tab:cyan'}
    for i in range(1,6):
        alpha = summary[summary['Unnamed: 0']=='alpha['+str(i)+']']
        alpha_m = 1-np.exp(-alpha['mean'].values[0])
        alpha_2_5 = 1-np.exp(-alpha['2.5%'].values[0])
        alpha_25 = 1-np.exp(-alpha['25%'].values[0])
        alpha_75 = 1-np.exp(-alpha['75%'].values[0])
        alpha_97_5 = 1-np.exp(-alpha['97.5%'].values[0])
        ax.plot([i-0.25,i+0.25],[alpha_m,alpha_m],color = alpha_colors[i-1])
        ax.plot([i]*2,[alpha_2_5,alpha_97_5],  marker = '_',color = alpha_colors[i-1])
        rect = Rectangle((i-0.25,alpha_25),0.5,alpha_75-alpha_25,linewidth=1, color = alpha_colors[i-1], alpha = 0.3)
        ax.add_patch(rect)
    ax.set_ylim([0,1])
    ax.set_ylabel('Fractional reduction in R0')
    ax.set_xticks([1,2,3,4,5])
    ax.set_xticklabels(['retail and recreation', 'grocery and pharmacy', 'transit stations','workplace', 'residential'],rotation='vertical')
    plt.tight_layout()
    fig.savefig(outdir+'plots/alphas.png', format='png', dpi=300)
    plt.close()

    #plot per country
    #Read in intervention dates
    intervention_df = pd.read_csv(datadir+'interventions_only.csv')
    result_file = open(outdir+'plots/summary_means.csv', 'w')
    result_file.write('Country,Epidemic Start,R0 at start,R0 29 Mar,R0 Apr 19\n') #Write headers
    for i in range(1,len(subregions)+1):

        country= countries[i-1]
        country_npi = intervention_df[intervention_df['Country']==country]
        #Get att stan data for country i
        dates = stan_data['dates_by_country'][:,i-1]
        observed_country_deaths = stan_data['deaths_by_country'][:,i-1]
        observed_country_cases = stan_data['cases_by_country'][:,i-1]
        end = int(stan_data['days_by_country'][i-1]) #3 week forecast #End of data for country i
        country_retail = stan_data['retail_and_recreation_percent_change_from_baseline'][:,i-1]
        country_grocery= stan_data['grocery_and_pharmacy_percent_change_from_baseline'][:,i-1]
        country_transit = stan_data['transit_stations_percent_change_from_baseline'][:,i-1]
        country_work = stan_data['workplaces_percent_change_from_baseline'][:,i-1]
        country_residential = stan_data['residential_percent_change_from_baseline'][:,i-1]
        #Print final mobility value
        print(country,country_grocery[end-1])

        #Extract modeling results
        means = {'prediction':np.zeros((days_to_simulate)),'E_deaths':np.zeros((days_to_simulate)), 'Rt':np.zeros((days_to_simulate))}
        lower_bound = {'prediction':np.zeros((days_to_simulate)),'E_deaths':np.zeros((days_to_simulate)), 'Rt':np.zeros((days_to_simulate))} #Estimated 2.5 %
        higher_bound = {'prediction':np.zeros((days_to_simulate)),'E_deaths':np.zeros((days_to_simulate)), 'Rt':np.zeros((days_to_simulate))} #Estimated 97.5 % - together 95 % CI
        lower_bound25 = {'prediction':np.zeros((days_to_simulate)),'E_deaths':np.zeros((days_to_simulate)), 'Rt':np.zeros((days_to_simulate))} #Estimated 25%
        higher_bound75 = {'prediction':np.zeros((days_to_simulate)),'E_deaths':np.zeros((days_to_simulate)), 'Rt':np.zeros((days_to_simulate))} #Estimated 55 % - together 75 % CI
        #Get means and 95 % CI for cases (prediction), deaths and Rt for all time steps
        for j in range(1,days_to_simulate+1):
            for var in ['prediction', 'E_deaths','Rt']:
                    var_ij = summary[summary['Unnamed: 0']==var+'['+str(j)+','+str(i)+']']
                    means[var][j-1]=var_ij['mean'].values[0]
                    lower_bound[var][j-1]=var_ij['2.5%'].values[0]
                    higher_bound[var][j-1]=var_ij['97.5%'].values[0]
                    lower_bound25[var][j-1]=var_ij['25%'].values[0]
                    higher_bound75[var][j-1]=var_ij['75%'].values[0]


        #Plot cases
        #Per day
        plot_shade_ci(days, end, dates[0], means['prediction'], observed_country_cases,lower_bound['prediction'],
        higher_bound['prediction'], lower_bound25['prediction'], higher_bound75['prediction'], 'Cases per day',
        outdir+'plots/'+country+'_cases.png',country_npi, country_retail, country_grocery, country_transit,
        country_work, country_residential, short_dates)

        #Cumulative
        plot_shade_ci(days, end, dates[0],np.cumsum(means['prediction']), np.cumsum(observed_country_cases),np.cumsum(lower_bound['prediction']),
        np.cumsum(higher_bound['prediction']), np.cumsum(lower_bound25['prediction']), np.cumsum(higher_bound75['prediction']),
        'Cumulative cases',outdir+'plots/'+country+'_cumulative_cases.png',country_npi, country_retail, country_grocery, country_transit, country_work, country_residential, short_dates)
        #Plot Deaths
        #Per day
        plot_shade_ci(days, end,dates[0],means['E_deaths'],observed_country_deaths, lower_bound['E_deaths'], higher_bound['E_deaths'],
        lower_bound25['E_deaths'], higher_bound75['E_deaths'], 'Deaths per day',
        outdir+'plots/'+country+'_deaths.png',country_npi, country_retail, country_grocery, country_transit, country_work, country_residential, short_dates)
        #Cumulative
        plot_shade_ci(days, end,dates[0],np.cumsum(means['E_deaths']),np.cumsum(observed_country_deaths), np.cumsum(lower_bound['E_deaths']), np.cumsum(higher_bound['E_deaths']),
        np.cumsum(lower_bound25['E_deaths']), np.cumsum(higher_bound75['E_deaths']), 'Cumulative deaths',
        outdir+'plots/'+country+'_cumulative_deaths.png',country_npi, country_retail, country_grocery, country_transit, country_work, country_residential, short_dates)
        #Plot R
        plot_shade_ci(days,end,dates[0],means['Rt'],'', lower_bound['Rt'], higher_bound['Rt'], lower_bound25['Rt'],
        higher_bound75['Rt'],'Rt',outdir+'plots/'+country+'_Rt.png',country_npi,
        country_retail, country_grocery, country_transit, country_work, country_residential, short_dates)

        #Print R mean at beginning and end of model
        try:
            result_file.write(country+','+str(dates[0])+','+str(np.round(means['Rt'],2))+','+str(np.round(means['Rt'][end,:],2))+'\n')#Print for table
        except:
            continue
    #Close outfile
    result_file.close()

    return None

def mcmc_parcoord(cat_array, xtick_labels, outdir):
    '''Plot parameters for each iteration next to each other as in the R fucntion mcmc_parcoord
    '''
    xtick_labels.insert(0,'')
    fig, ax = plt.subplots(figsize=(8, 8))
    for i in range(2000,cat_array.shape[0]): #loop through all iterations
            ax.plot(np.arange(cat_array.shape[1]), cat_array[i,:], color = 'k', alpha = 0.1)
    ax.plot(np.arange(cat_array.shape[1]), np.median(cat_array, axis = 0), color = 'r', alpha = 1)
    ax.set_xticklabels(xtick_labels,rotation='vertical')
    ax.set_ylim([-5,20])
    plt.tight_layout()
    fig.savefig(outdir+'plots/mcmc_parcoord.png', format = 'png')
    plt.close()

def plot_shade_ci(x,end,start_date,y, observed_y, lower_bound, higher_bound,lower_bound25, higher_bound75,ylabel,outname,country_npi, country_retail, country_grocery, country_transit, country_work, country_residential, short_dates):
    '''Plot with shaded 95 % CI (plots both 1 and 2 std, where 2 = 95 % interval)
    '''
    dates = np.arange(start_date,np.datetime64('2020-05-27')) #Get dates - increase for longer foreacast
    selected_short_dates = np.array(short_dates[short_dates['np_date'].isin(dates)]['short_date']) #Get short version of dates


    if len(dates) != len(selected_short_dates):
        pdb.set_trace()
    forecast = end+21
    fig, ax1 = plt.subplots(figsize=(4, 2.5))

    #Plot observed dates
    if len(observed_y)>1:
        ax1.bar(x[:end],observed_y[:end], alpha = 0.5) #3 week forecast

    #Plot simulation
    ax1.plot(x[:end],y[:end], alpha=0.5, linewidth = 2.0, color = 'b')
    ax1.fill_between(x[:end], lower_bound[:end], higher_bound[:end], color='cornflowerblue', alpha=0.4)
    ax1.fill_between(x[:end], lower_bound25[:end], higher_bound75[:end], color='cornflowerblue', alpha=0.6)

    #Plot predicted dates
    ax1.plot(x[end-1:forecast],y[end-1:forecast], alpha=0.5, linewidth = 2.0, color = 'g')
    ax1.fill_between(x[end-1:forecast], lower_bound[end-1:forecast] ,higher_bound[end-1:forecast], color='forestgreen', alpha=0.4)
    ax1.fill_between(x[end-1:forecast], lower_bound25[end-1:forecast], higher_bound75[end-1:forecast], color='forestgreen', alpha=0.6)


    #Plot NPIs
    #NPIs
    NPI = ['public_events', 'schools_universities',  'lockdown',
        'social_distancing_encouraged', 'self_isolating_if_ill']
    NPI_labels = {'schools_universities':'schools and universities',  'public_events': 'public events', 'lockdown': 'lockdown',
        'social_distancing_encouraged':'social distancing encouraged', 'self_isolating_if_ill':'self isolating if ill'}
    NPI_markers = {'schools_universities':'*',  'public_events': 'X', 'lockdown': 's',
        'social_distancing_encouraged':'p', 'self_isolating_if_ill':'d'}
    NPI_colors = {'schools_universities':'k',  'public_events': 'blueviolet', 'lockdown': 'mediumvioletred',
        'social_distancing_encouraged':'maroon', 'self_isolating_if_ill':'darkolivegreen'}


    y_npi =max(higher_bound[:forecast])*0.9
    y_step = y_npi/20
    npi_xvals = [] #Save npi xvals to not plot over each npi
    for npi in NPI:
        try:
            if country_npi[npi].values[0] == '0': #If nan
                continue
            xval = np.where(dates==np.datetime64(country_npi[npi].values[0]))[0][0]
            ax1.axvline(xval, linestyle='--', linewidth=0.5, c= 'b')
            if xval in npi_xvals:
                ax1.scatter(xval, y_npi-y_step, s = 12, marker = NPI_markers[npi], color = NPI_colors[npi])
            else:
                ax1.scatter(xval, y_npi, s = 12, marker = NPI_markers[npi], color = NPI_colors[npi])
            npi_xvals.append(xval)
        except:
            break


    #Plot mobility data
    #Use a twin of the other x axis
    ax2 = ax1.twinx()  # instantiate a second axes that shares the same x-axis
    ax2.plot(x[:end],country_retail[:end], alpha=0.5, color='tab:red', linewidth = 1.0)
    ax2.plot(x[:end],country_grocery[:end], alpha=0.5, color='tab:purple', linewidth = 1.0)
    ax2.plot(x[:end],country_transit[:end], alpha=0.5, color='tab:pink', linewidth = 1.0)
    ax2.plot(x[:end],country_work[:end], alpha=0.5, color='tab:olive', linewidth = 1.0)
    ax2.plot(x[:end],country_residential[:end], alpha=0.5, color='tab:cyan', linewidth = 1.0)

    #Plot formatting
    #ax1
    ax1.set_ylabel(ylabel)
    ax1.set_ylim([0,max(higher_bound[:forecast])])
    xticks=np.arange(forecast-1,0,-7)
    ax1.set_xticks(xticks)
    try:
        ax1.set_xticklabels(selected_short_dates[xticks],rotation='vertical')
    except:
        pdb.set_trace()
    #ax2
    ax2.set_ylim([-1,0.4])
    #fig
    fig.tight_layout()
    fig.savefig(outname, format = 'png')
    #fig.savefig(outname.split('.png')[0]+'.svg', format = 'svg')
    plt.close()


#####MAIN#####
#Set font size
matplotlib.rcParams.update({'font.size': 12})
args = parser.parse_args()
datadir = args.datadir[0]
countries = args.countries[0].split(',')
subregions = args.subregions[0].split(',')
epidemic_data = pd.read_csv(args.epidemic_data[0])
days_to_simulate=args.days_to_simulate[0] #Number of days to model. Increase for further forecast
end_date = np.datetime64(args.end_date[0])
short_dates = pd.read_csv(args.short_dates[0])

#Make sure the np dates are in the correct format
short_dates['np_date'] = pd.to_datetime(short_dates['np_date'], format='%Y/%m/%d')
outdir = args.outdir[0]
#Covariate names
covariate_names = ['retail_and_recreation_percent_change_from_baseline',
'grocery_and_pharmacy_percent_change_from_baseline',
'transit_stations_percent_change_from_baseline',
'workplaces_percent_change_from_baseline',
'residential_percent_change_from_baseline']

#Read data
stan_data = read_and_format_data(datadir, countries, subregions, epidemic_data, days_to_simulate, covariate_names, end_date)

#Visualize
visualize_results(outdir, subregions, stan_data, days_to_simulate, short_dates)
