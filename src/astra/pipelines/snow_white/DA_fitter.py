import numpy as np
import sys
import matplotlib.pyplot as plt
from scipy import optimize
import fitting_scripts
import emulator_DA
from scipy import interpolate
import datetime
import os
import pickle
from scipy import linalg
import model_processing
import get_line_info_v3
from astropy.io import fits

c = 299792.458 # Speed of light in km/s
plot = True # True to display plot at the end of fitting

#-------------------------------------------------------------------------------------------------
# Loads the input spectrum as command line argument
#try:
 #   spectra=np.loadtxt(sys.argv[1],usecols=(0,1,2),delimiter=",",unpack=True).transpose()
#except:
 #   spectra=np.loadtxt(sys.argv[1],usecols=(0,1,2),unpack=True).transpose()
#-----------------------------------------------------------------------------------------------------
hdul = fits.open(sys.argv[1])
flux=hdul[1].data["FLUX"]*1e-17
wave=10**(hdul[1].data["LOGLAM"])
err=np.sqrt(hdul[1].data["IVAR"])*1e-17
flux=flux[ivar!=0.]
wave=wave[ivar!=0.]
ivar=ivar[ivar!=0.]
err=(1/np.sqrt(ivar))*1e-17
wave=wave[(np.isnan(flux)==False)]
err=err[(np.isnan(flux)==False)]
flux=flux[(np.isnan(flux)==False)]
err=err[(wave>=3650)&(wave<9800)]
flux=flux[(wave>=3650)&(wave<9800)]
wave=wave[(wave>=3650)&(wave<9800)]

parallax=hdul[2].data["PARALLAX"]
Gmag=hdul[2].data["GAIA_G_MAG"]
wave_a=wave#/(1.0 + 2.735182e-4 + 131.4182/wave**2 + 2.76249e8/wave**4) #models are now in vacuum wavelength so no need for conversion

#=============================Classify WD spectrum==========================
with open('training_file_v3', 'rb') as f:
        kf = pickle._load(f,fix_imports=True)
labels= get_line_info_v3.line_info(wave_a,flux,err)
predictions = kf.predict(labels.reshape(1, -1))
probs = kf.predict_proba(labels.reshape(1, -1))
first= probs[0][kf.classes_==predictions[0]]
if first >=0.5:
    p_class=predictions[0]
else:
    second=sorted(probs[0])[-2]
    if second/first>0.6:
        p_class=predictions[0]+"/"+kf.classes_[probs[0]==second]
    else:
        p_class=predictions[0]+":"

print("Classified as:", p_class)
if p_class=="DA" or p_class=="DA:":

    spectra=np.stack((wave,flux,err),axis=-1)
    spectra = spectra[(np.isnan(spectra[:,1])==False) & (spectra[:,0]>3800)& (spectra[:,0]<7950)]
    spec_w=wave


    #normilize spectrum
    spec_n, cont_flux = fitting_scripts.norm_spectra(spectra,model=False)
    #load lines to fit and crops them
    line_crop = np.loadtxt('line_crop.dat')
    l_crop = line_crop[(line_crop[:,0]>spec_w.min()) & (line_crop[:,1]<spec_w.max())]

    #fit entire grid to find good starting point
    lines_sp,lines_mod,best_grid,grid_param,grid_chi=fitting_scripts.fit_grid(spec_n,line_crop)

    first_T=grid_param[grid_chi==np.min(grid_chi)][0][0]
    first_g=grid_param[grid_chi==np.min(grid_chi)][0][1]
    if first_T>=16000 and first_T<=40000:
        line_crop = np.loadtxt('line_crop.dat')
        l_crop = line_crop[(line_crop[:,0]>spec_w.min()) & (line_crop[:,1]<spec_w.max())]
    elif first_T>=8000 and first_T<16000:
        line_crop = np.loadtxt('line_crop_cool.dat')
        l_crop = line_crop[(line_crop[:,0]>spec_w.min()) & (line_crop[:,1]<spec_w.max())]
    elif first_T<8000:
        line_crop = np.loadtxt('line_crop_vcool.dat')
        l_crop = line_crop[(line_crop[:,0]>spec_w.min()) & (line_crop[:,1]<spec_w.max())]
    elif first_T>40000:
        line_crop = np.loadtxt('line_crop_hot.dat')
        l_crop = line_crop[(line_crop[:,0]>spec_w.min()) & (line_crop[:,1]<spec_w.max())]

#-----------------------load PCA files------------------------------------------------------
    wref=np.load("wref.npy")
    with open("emu_file", 'rb') as pickle_file:
        emu= pickle.load(pickle_file)
#-----------------------------------------------------------------------------------------

    print(first_T,first_g)

#this calls the scripts in fitting_scipts and does the actual fitting
    new_best= optimize.minimize(fitting_scripts.fit_func,(first_T,first_g,30.)
                            ,bounds=((3000,80000),(705,949),(-300,300))
                            ,args=(spec_n,l_crop,emu,wref,0,),method="Nelder-Mead")



    best_T, best_g, best_rv = new_best.x[0], new_best.x[1], new_best.x[2]

    T_max=best_T+500
    if T_max>80000:
        T_max=80000

    T_min=best_T-500
    if T_min<3000:
        T_min=3000

    g_max=best_g+10
    if g_max>949:
        g_max=949

    g_min=best_g-10
    if g_min<700:
        g_min=701
    print(best_T,best_g)

    #repeat fit using best solution and least square to find errors
    err_best= optimize.least_squares(fitting_scripts.fit_func,(first_T, best_g, best_rv),bounds=([3000,701,best_rv-10],[80000,949,best_rv+10]),args=(spec_n,l_crop,emu,wref,2),method="trf")
    U, s, Vh = linalg.svd(err_best.jac, full_matrices=False)
    tol = np.finfo(float).eps*s[0]*max(err_best.jac.shape)
    w = s > tol
    cov = (Vh[w].T/s[w]**2) @ Vh[w]  # robust covariance matrix
    perr = np.sqrt(np.diag(cov))

#====================find second solution and repeat everything again#==============================================
    if first_T <=13000.:
        tmp_Tg,tmp_chi= grid_param[grid_param[:,0]>13000.], grid_chi[grid_param[:,0]>13000.]
        second_T= tmp_Tg[tmp_chi==np.min(tmp_chi)][0][0]
        second_g= tmp_Tg[tmp_chi==np.min(tmp_chi)][0][1]
    elif first_T >13000.:
        tmp_Tg,tmp_chi= grid_param[grid_param[:,0]<13000.], grid_chi[grid_param[:,0]<13000.]
        second_T= tmp_Tg[tmp_chi==np.min(tmp_chi)][0][0]
        second_g= tmp_Tg[tmp_chi==np.min(tmp_chi)][0][1]


    if second_T>=16000 and second_T<=40000:
        line_crop = np.loadtxt('line_crop.dat')
        l_crop = line_crop[(line_crop[:,0]>spec_w.min()) & (line_crop[:,1]<spec_w.max())]
    elif second_T>=8000 and second_T<16000:
        line_crop = np.loadtxt('line_crop_cool.dat')
        l_crop = line_crop[(line_crop[:,0]>spec_w.min()) & (line_crop[:,1]<spec_w.max())]
    elif second_T<8000:
        line_crop = np.loadtxt('line_crop_vcool.dat')
        l_crop = line_crop[(line_crop[:,0]>spec_w.min()) & (line_crop[:,1]<spec_w.max())]
    elif second_T>40000:
        line_crop = np.loadtxt('line_crop_hot.dat')
        l_crop = line_crop[(line_crop[:,0]>spec_w.min()) & (line_crop[:,1]<spec_w.max())]

    if best_T>=13000:
            new_best2= optimize.minimize(fitting_scripts.fit_func,(8000,750,best_rv),
                                 bounds=((3000,13000),(701,949),(-300,300))
                                         ,args=(spec_n,l_crop,emu,wref,0),method="Nelder-Mead")
    elif best_T<13000:
        new_best2= optimize.minimize(fitting_scripts.fit_func,(second_T,second_g,best_rv),
                                 bounds=((13000,80000),(705,949),(-300,300))
                                         ,args=(spec_n,l_crop,emu,wref,0),method="Nelder-Mead")

    best_T2, best_g2, best_rv2 = new_best2.x[0], new_best2.x[1], new_best2.x[2]


    T_max2=best_T2+500
    if T_max2>80000:
        T_max2=80000

    T_min2=best_T2-500
    if T_min2<3000:
        T_min2=3000

    g_max2=best_g2+10
    if g_max2>949:
        g_max2=949

    g_min2=best_g2-10
    if g_min2<651:
        g_min2=651

    #err_best2= optimize.least_squares(fitting_scripts.fit_func,(best_T2, best_g2, best_rv2),bounds=([T_min2,g_min2,best_rv2-10],[T_max2,g_max2,best_rv2+10]),args=(spec_n,l_crop,emu,wref,2),method="trf")
    err_best2= optimize.least_squares(fitting_scripts.fit_func,(second_T, best_g2, best_rv2),bounds=([3000,701,best_rv2-10],[80000,949,best_rv2+10]),args=(spec_n,l_crop,emu,wref,2),method="trf")

    U, s, Vh = linalg.svd(err_best2.jac, full_matrices=False)
    tol = np.finfo(float).eps*s[0]*max(err_best2.jac.shape)
    w = s > tol
    cov = (Vh[w].T/s[w]**2) @ Vh[w]  # robust covariance matrix
    #perr2 = np.sqrt(np.diag(cov))
    T2_err=np.sqrt(np.diag(cov))[0]*3
    g2_err=np.sqrt(np.diag(cov))[1]
    

#========================use gaia G mag and parallax to solve for hot vs cold solution
    
    T_true=fitting_scripts.hot_vs_cold(best_T,best_g/100,best_T2,best_g2/100,parallax,Gmag,emu,wref)
    if T_true==best_T:
        print("Solution: Teff=",best_T,"+-",perr[0]," log g=",best_g,"+-",perr[1]," rv=",best_rv)#,"+-",perr[2])
    elif T_true==best_T2:
        
        print("Solution: Teff=",best_T2,"+-",T2_err," log g=",best_g2,"+-",g2_err," rv=",best_rv2)#,"+-",perr2[2])



#=======================plotting===============================================
    if plot == True:
    # Get and save the 2 best lines from the spec and model, and the full models
        lines_s,lines_m,mod_n=fitting_scripts.fit_func((best_T,best_g,best_rv),
                                                   spec_n,l_crop,emu,wref,mode=1)
    
        lines_s_o,lines_m_o,mod_n_o=fitting_scripts.fit_func((best_T2,best_g2,best_rv),
                                                         spec_n,l_crop,emu,wref,mode=1)
        fig=plt.figure(figsize=(8,5))
        ax1 = plt.subplot2grid((1,4), (0, 3),rowspan=3)
        step = 0
        for i in range(0,len(lines_s)): # plots Halpha (i=0) to H6 (i=5)
            min_p   = lines_s[i][:,0][lines_s[i][:,1]==np.min(lines_s[i][:,1])][0]
            min_p_o = lines_s_o[i][:,0][lines_s_o[i][:,1]==np.min(lines_s_o[i][:,1])][0]
            ax1.plot(lines_s[i][:,0]-min_p,lines_s[i][:,1]+step,color='k')
            ax1.plot(lines_s[i][:,0]-min_p,lines_m[i]+step,color='r')
            ax1.plot(lines_s_o[i][:,0]-min_p_o,lines_m_o[i]+step,color='g')
            step+=0.5
        xticks = ax1.xaxis.get_major_ticks()
        ax1.set_xticklabels([])
        ax1.set_yticklabels([])

        ax2 = plt.subplot2grid((3,4), (0, 0),colspan=3,rowspan=2)
        #try:
        #    full_spec=np.loadtxt(sys.argv[1],usecols=(0,1),delimiter=",",unpack=True).transpose()
        #except:
        #    full_spec=np.loadtxt(sys.argv[1],usecols=(0,1),unpack=True).transpose()
        full_spec=np.stack((wave,flux,err),axis=-1)
        full_spec = full_spec[(np.isnan(full_spec[:,1])==False) & (full_spec[:,0]>3500)& (full_spec[:,0]<7900)]
        

    # Adjust the flux of models to match the spectrum
        check_f_spec=full_spec[:,1][(full_spec[:,0]>4500.) & (full_spec[:,0]<4550.)]
        check_f_model=mod_n[:,1][(mod_n[:,0]>4500.) & (mod_n[:,0]<4550.)]
        adjust=np.average(check_f_model)/np.average(check_f_spec)
        ax2.plot(full_spec[:,0],full_spec[:,1],color='k')
        ax2.plot(mod_n[:,0]*(best_rv+c)/c,(mod_n[:,1]/adjust),color='r')
    
        check_f_model_o=mod_n_o[:,1][(mod_n_o[:,0]>4500.) & (mod_n_o[:,0]<4550.)]
        adjust_o=np.average(check_f_model_o)/np.average(check_f_spec)
        ax2.plot(mod_n_o[:,0]*(best_rv+c)/c,mod_n_o[:,1]/adjust_o,color='g')

        ax2.set_ylabel(r'F$_{\lambda}$ [erg cm$^{-2}$ s$^{-1} \AA^{-1}$]',fontsize=12)
        ax2.set_xlabel(r'Wavelength $(\AA)$',fontsize=12)
        ax2.set_xlim([3400,5600])
        ax3 = plt.subplot2grid((3,4), (2, 0),colspan=3,rowspan=1,sharex=ax2)

        flux_i = interpolate.interp1d(mod_n[:,0]*(best_rv+c)/c,mod_n[:,1]/adjust,kind='linear')(full_spec[:,0])
        wave3=full_spec[:,0]
        flux3=full_spec[:,1]/flux_i
        binsize=1
        xdata3=[]
        ydata3=[]
        for i in range(0,(np.size(wave3)-binsize),binsize):
            xdata3.append(np.average(wave3[i:i+binsize]))
            ydata3.append(np.average(flux3[i:i+binsize]))
        plt.plot(xdata3,ydata3)

        plt.hlines(1.02, 3400,5600,colors="r")
        plt.hlines(1.01, 3400,5600,colors="0.5",ls="--")
        plt.hlines(0.98, 3400,5600,colors="r")
        plt.hlines(0.99, 3400,5600,colors="0.5",ls="--")
        ax3.set_xlim([3400,5600])
        ax3.set_ylim([0.95,1.04])
        plt.show()
        #plt.close()
