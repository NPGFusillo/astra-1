module Grok
using HDF5, Optim, FITSIO, Interpolations, Korg, ProgressMeter
using DSP: gaussian, conv  # used for vsini and continuum adjustment
using SparseArrays: spzeros # used for crazy continuum adjustment
using FastRunningMedian: running_median
using Polynomials
using Distributed
using SharedArrays


_data_dir = joinpath(@__DIR__, "../data") 
_data_dir = @__DIR__
# TODO addprocs

"""
Make sure that there are at least `n` workers available.  
"""
function ensure_workers(n)
    if nworkers() < n
        addprocs(n - nworkers())
    elseif nworkers() > n
        @warn "$n workers requested, but there are already $(nworkers()) workers. Will you run out of memory?"
    end
end

#####################################################################
# TODO these should be excised from the module
# read the mask that is aplied to all spectra
const ferre_mask = parse.(Bool, readlines(joinpath(_data_dir, "ferre_mask.dat")));
const ferre_wls = (10 .^ (4.179 .+ 6e-6 * (0:8574)))
const regions = [
    (15152.0, 15800.0),
    (15867.0, 16424.0),
    (16484.0, 16944.0), 
]
const region_inds = map(regions) do (lb, ub)
    findfirst(ferre_wls .> lb) : (findfirst(ferre_wls .> ub) - 1)
end
#####################################################################

"""
We don't use Korg's `apply_rotation` because this is specialed for the case where wavelenths are 
log-uniform.  We can use FFT-based convolution to apply the rotation kernel to the spectrum in this 
case.
"""
function apply_rotation(flux, vsini; ε=0.6, log_lambda_step=1.3815510557964276e-5)
    if vsini == 0
        return flux
    end

    # calculate log-lamgda step from the wavelength grid
    # log_lambda_step = mean(diff(log.(ferre_wls)))

    # half-width of the rotation kernel in Δlnλ
    Δlnλ_max = vsini * 1e5 / Korg.c_cgs
    # half-width of the rotation kernel in pixels
    p = Δlnλ_max / log_lambda_step
    # Δlnλ detuning for each pixel in kernel
    Δlnλs = [-Δlnλ_max ; (-floor(p) : floor(p))*log_lambda_step ; Δlnλ_max]
    
    # kernel coefficients
    c1 = 2(1-ε)
    c2 = π * ε / 2
    c3 = π * (1-ε/3)
    
    x = @. (1 - (Δlnλs/Δlnλ_max)^2)
    rotation_kernel = @. (c1*sqrt(x) + c2*x)/(c3 * Δlnλ_max)
    rotation_kernel ./= sum(rotation_kernel)
    offset = (length(rotation_kernel) - 1) ÷ 2

    conv(rotation_kernel, flux)[offset+1 : end-offset]
end

function fill_chip_gaps!(flux)
    Δ = 10 # insurance
    # set the off-chip flux values to be reasonable, so as to not have crazy edge effects
    flux[1:region_inds[1][1]] .= flux[region_inds[1][1] + Δ]
    flux[region_inds[end][end]:end] .= flux[region_inds[end][end] - Δ]
    for (i1, i2) in [(region_inds[1][end], region_inds[2][1]), (region_inds[2][end], region_inds[3][1])]
        flux[i1:i2] .= range(start=flux[i1-Δ], stop=flux[i2+Δ], length=i2-i1 + 1)
    end
end

function apply_smoothing_filter!(flux, kernel_width=150;
                                kernel_pixels=301)
                                
    @assert isodd(kernel_pixels) # required for offset math to work
    sampled_kernel = gaussian(kernel_pixels, kernel_width/kernel_pixels)
    sampled_kernel ./= sum(sampled_kernel) # normalize (everything should cancel in the end, but I'm paranoid)
    offset = (length(sampled_kernel) - 1) ÷ 2

    map(region_inds) do r
        buffered_region = r[1]-offset : r[end]+offset
        flux[buffered_region] = conv(sampled_kernel, flux[buffered_region])[offset+1 : end-offset]
    end
end

"""
This loads a grok model grid into a SharedArray.
"""
<<<<<<< HEAD
function load_grid(grid_path; use_subset=true, v_sinis=nothing, ε=0.6, fill_non_finite=10.0, 
                   use_median_ratio=false, old_grid=false, 
                   metallicity_parameter_name= (old_grid ? "metallicity_vals" : "m_h_vals"))
=======


function load_grid(grid_path; use_subset=true, v_sinis=nothing, ε=0.6, fill_non_finite=10.0)
>>>>>>> dff23b1 (grok jl)
    model_spectra = h5read(grid_path, "spectra")

    if !isnothing(fill_non_finite)
        model_spectra[isnan.(model_spectra)] .= fill_non_finite
    end

    # TODO make it possible to not hardcode the specific parameters?
    teffs = h5read(grid_path, "Teff_vals")
    loggs = h5read(grid_path, "logg_vals")
    v_mics = h5read(grid_path, "vmic_vals")
    m_hs = h5read(grid_path, metallicity_parameter_name)

    if old_grid
        model_spectra = model_spectra[:, :, :, 2, :]
        grid_points = [teffs, loggs, m_hs]
        labels = ["teff", "logg", "m_h"]
    elseif use_subset
        model_spectra = model_spectra[:, :, :, 2, :, 3, 3]
        grid_points = [teffs, loggs, m_hs]
        labels = ["teff", "logg", "m_h"]
    else
        c_ms = h5read(grid_path, "c_m_vals")
        n_ms = h5read(grid_path, "n_m_vals")
        labels = ["teff", "logg", "v_micro", "m_h", "c_m", "n_m"]
        grid_points = [teffs, loggs, v_mics, m_hs, c_ms, n_ms]
    end

    if !isnothing(v_sinis)

        # make it a matrix with each row a spectrum
        model_spectra = reshape(model_spectra, (size(model_spectra, 1), :))

        _model_spectra = Array{Float64}(undef, (size(model_spectra, 1),  
                                                prod(collect(size(model_spectra)[2:end])),
                                                length(v_sinis)))

        # apply each kernel to model spectra to add a new dimention to the grid
        for (i, v_sini) in enumerate(v_sinis)
            for j in 1:size(model_spectra, 2)
                rotF = apply_rotation(model_spectra[:, j], v_sini, ε=ε)
                if all(rotF .== 0)
                    println("all null")
                end
                _model_spectra[:, j, i] = rotF #apply_rotation(model_spectra[:, j], v_sini, ε=ε)
            end
            # apply the kernel to each spectrum
            #_model_spectra[:, :, i] = kernel * model_spectra
        end

        push!(grid_points, v_sinis)
        push!(labels, "v_sini")
        
        model_spectra = reshape(_model_spectra, (size(model_spectra, 1), length.(grid_points)...))
    end

<<<<<<< HEAD
    # apply the global ferre mask, and (if not using a running media of the ratio) divide out a 
    # moving mean
    filtered_spectra = if use_median_ratio
        model_spectra[ferre_mask, (1:s for s in size(model_spectra)[2:end])...]
    else
        # reshape the model spectra to be a 2D array w/ first dimension corresponding to wavelength 
        # and apply the global ferre mask
        stacked_model_spectra = reshape(model_spectra, (size(model_spectra, 1), :))
        convolved_inv_model_flux = 1 ./ stacked_model_spectra
        @showprogress desc="conv'ing inverse models" for i in 1:size(stacked_model_spectra, 2)
            apply_smoothing_filter!(view(convolved_inv_model_flux, :, i))
        end
        filtered_spectra = (stacked_model_spectra .* convolved_inv_model_flux)[ferre_mask, :]
        # reshape back. These have the convolved inverse model flux divided out already
        # (so the name is slightly wrong)
        reshape(filtered_spectra, (size(filtered_spectra, 1), size(model_spectra)[2:end]...))
    end

    # put model spectra in a shared array TODO make this memory-efficient
    spectra = SharedArray{Float64}(size(filtered_spectra))
    spectra .= filtered_spectra
=======
    # put model spectra in a shared array
    #spectra = SharedArray{Float64}(dims(model_spectra))
    #spectra .= model_spectra
>>>>>>> dff23b1 (grok jl)

    (labels, grid_points, model_spectra)
end

<<<<<<< HEAD
function get_best_subgrid(masked_model_spectra, slicer, flux, ivar, convF, use_median_ratio, ferre_mask)

    model_f  = view(masked_model_spectra, :, slicer...) 

    corrected_model_f = if use_median_ratio
        # if using running median of flux/model ratio, we have to do it now
        continua = (convF[ferre_mask, :] ./ model_f)
        stacked_continua = reshape(continua, (size(continua, 1), :))
        for i in 1:size(stacked_continua, 2)
            stacked_continua[:, i] .= running_median(stacked_continua[:, i], 151)
        end
        @assert continua[:] == stacked_continua[:] #TODO remove
        model_f .* continua
    else
        # in this case, model_f already has the filtered model flux divided out
        model_f .* convF[ferre_mask]
    end
=======

function prepare_kernel(width=150, pixels=301)
    sampled_kernel = gaussian(pixels, width/pixels)
    sampled_kernel ./= sum(sampled_kernel) # normalize (everything should cancel in the end, but I'm paranoid)
    offset = (length(sampled_kernel) - 1) ÷ 2
    (sampled_kernel, offset)
end

function convolve_and_mask_model_spectra(model_spectra, kernel, offset)
    stacked_model_spectra = reshape(model_spectra, (size(model_spectra, 1), :))
    convolved_inv_model_flux = 1 ./ stacked_model_spectra
    @showprogress desc="conv'ing inverse models" for i in 1:size(stacked_model_spectra, 2)
        convolved_inv_model_flux[:, i] = conv(kernel, convolved_inv_model_flux[:, i])[offset+1 : end-offset]
    end
    masked_model_spectra = (stacked_model_spectra .* convolved_inv_model_flux)[ferre_mask, :]
    masked_model_spectra = reshape(masked_model_spectra, (size(masked_model_spectra, 1), size(model_spectra)[2:end]...))
    convolved_inv_model_flux = reshape(convolved_inv_model_flux, (8575, size(masked_model_spectra)[2:end]...))
    (masked_model_spectra, convolved_inv_model_flux)
end


function load_old_grid(grid_path; fix_vmic=nothing, fill_non_finite=10.0, fix_off_by_one=false, 
                   v_sinis=nothing, ε=0.6)
    model_spectra = h5read(grid_path, "spectra")

    if !isnothing(fill_non_finite)
        model_spectra[isnan.(model_spectra)] .= fill_non_finite
    end

    # TODO make it possible to not hardcode the specific parameters?
    teffs = h5read(grid_path, "Teff_vals")
    loggs = h5read(grid_path, "logg_vals")
    v_mics = h5read(grid_path, "vmic_vals")
    m_hs = h5read(grid_path, "metallicity_vals")

    if !isnothing(fix_vmic)
        index = findfirst(v_mics .== fix_vmic)
        model_spectra = model_spectra[:, :, :, index, :]
        labels = ["teff", "logg", "m_h"]
        grid_points = [teffs, loggs, m_hs]
    else
        labels = ["teff", "logg", "v_micro", "m_h"]
        grid_points = [teffs, loggs, v_mics, m_hs]
    end

    if fix_off_by_one
        # TODO audit this
        model_spectra[2:end, :, :, :, :] .= model_spectra[1:end-1, :, :, :, :]
    end

    if !isnothing(v_sinis)

        # make it a matrix with each row a spectrum
        model_spectra = reshape(model_spectra, (size(model_spectra, 1), :))

        _model_spectra = Array{Float64}(undef, (size(model_spectra, 1),  
                                                prod(collect(size(model_spectra)[2:end])),
                                                length(v_sinis)))

        # apply each kernel to model spectra to add a new dimention to the grid
        for (i, v_sini) in enumerate(v_sinis)
            for j in 1:size(model_spectra, 2)
                rotF = apply_rotation(model_spectra[:, j], v_sini, ε=ε)
                if all(rotF .== 0)
                    println("all null")
                end
                _model_spectra[:, j, i] = rotF #apply_rotation(model_spectra[:, j], v_sini, ε=ε)
            end
            # apply the kernel to each spectrum
            #_model_spectra[:, :, i] = kernel * model_spectra
        end

        push!(grid_points, v_sinis)
        push!(labels, "v_sini")
        
        model_spectra = reshape(_model_spectra, (size(model_spectra, 1), length.(grid_points)...))
    end
    (labels, grid_points, model_spectra)
end

function get_best_subgrid(masked_model_spectra, slicer, flux, ivar, convF, ferre_mask)

    model_f  = view(masked_model_spectra, :, slicer...) 

    corrected_model_f = model_f .* convF[ferre_mask]
>>>>>>> dff23b1 (grok jl)

    chi2 = sum((corrected_model_f .- flux[ferre_mask, :]).^2 .* ivar[ferre_mask], dims=1)
    
    rel_index = collect(Tuple(argmin(chi2)))[2:end]

    # map the index to the full grid
    index = [s[ri] for (s, ri) in zip(slicer, rel_index)]
    (index, chi2)
end


"""
fluxes and ivar should be vectors or lists of the same length whose elements are vectors of length 
8575.
"""
function get_best_nodes(grid, fluxes, ivars, nmf_rectified_fluxes, continuums; refinement_levels=[4, 4, 2], minimum_nodes_per_dimension=3)
    fluxes = Vector{Float64}.(collect.(fluxes))
    ivars = Vector{Float64}.(collect.(ivars))
    nmf_rectified_fluxes = Vector{Float64}.(collect.(nmf_rectified_fluxes))
    continuums = Vector{Float64}.(collect.(continuums))

<<<<<<< HEAD
    # if we are not using a median ratio, the grid should be pre-filtered with a moving mean.
    labels, grid_points, masked_model_spectra = grid 
=======
    labels, grid_points, model_spectra = grid
    kernel, offset = prepare_kernel()    

    masked_model_spectra, convolved_inv_model_flux = convolve_and_mask_model_spectra(model_spectra, kernel, offset)
>>>>>>> dff23b1 (grok jl)


    grid_dims = size(masked_model_spectra)[2:end]
    out = Array{Any}(undef, length(fluxes))
    j = 1
    @showprogress pmap(fluxes, ivars, nmf_rectified_fluxes, continuums) do flux, ivar, nmf_rectified_flux, continuum

        convF = conv(kernel, nmf_rectified_flux)[offset+1 : end-offset]
        convF = convF .* continuum
        # ignore first and last 200 pixels in chi2 calculation
        # 50 pixels because the NMF model is cut off, and 150 for the width of the filter
        ivar[ivar .< 1e-8] .= 0
        ivar[1:201] .= 0
        ivar[end-200:end] .= 0

        ivar[convF .== 0] .= 0
        ivar[flux .== 0] .= 0

        slicer = [unique([range(start=1, step=first(refinement_levels), stop=stop)...; stop]) for stop in grid_dims]
        index, chi2 = get_best_subgrid(masked_model_spectra, slicer, flux, ivar, convF, ferre_mask)        
        
        #fig, ax = plt.subplots()
        #ax.plot(ferre_wls, flux)
        #ax.plot(ferre_wls[ferre_mask], masked_model_spectra[:, index...] .* convF[ferre_mask], c="tab:red")
        #fig.savefig("/uufs/chpc.utah.edu/common/home/u6020307/tmp4.png")


        for refinement_level in refinement_levels[2:end]
            # create a slicer to take a volume around the current index
            n_points_per_side = max.(minimum_nodes_per_dimension / 2, grid_dims ./ (2 * refinement_level))
        
            s_indices = Int.(floor.(max.(index .- n_points_per_side, 1)))
            e_indices = Int.(ceil.(min.(index .+ n_points_per_side, collect(grid_dims))))
        
            # ensure that we have at least 3 points per dimension?
            e_indices = min.(s_indices .+ max.(e_indices .- s_indices, minimum_nodes_per_dimension), collect(grid_dims))
            s_indices = max.(e_indices .- max.(e_indices .- s_indices, minimum_nodes_per_dimension), 1)
        
            slicer = [[range(start=start, stop=stop)...] for (start, stop) in zip(s_indices, e_indices)]
                
            index, chi2 = get_best_subgrid(masked_model_spectra, slicer, flux, ivar, convF, ferre_mask)
        
            #print(refinement_level, " ", n_points_per_side, " ", s_indices, " ", e_indices, "\n")
            #print(refinement_level, " ", e_indices .- s_indices, "\n")
            #print(index, " ", minimum(chi2), "\n")
        end
        
        # fit a quadratic in each dimension
        best_fit_value = []
        for i in 1:length(index)
            dims = [1:(1 + length(index))...] # the offset here and next is to handle the singleton dimension
            deleteat!(dims, i + 1)
            
            x = grid_points[i][slicer[i]]
            y = [minimum(chi2, dims=dims)...]
        
            # fit a quadratic to the minima
            idx = argmin(y)
            si = max(1, idx-1)
            ei = min(length(y), idx+1)
            if (ei - si) < 3
                if ei == length(y)
                    si = length(y) - 2
                else
                    ei = si + 2
                end
            end
        
            poly = fit(x[si:ei], y[si:ei], 2)

            x_min = try
                if last(poly.coeffs) > 0
                    # if the quadratic is concave up, then the minimum is at the vertex
                    -poly.coeffs[2] / (2 * poly.coeffs[3])
                else
                    # if the quadratic is concave down, then the minimum is at the edge
                    x[argmin(y)]
                end
            catch e
                println("fail ", si, " ", ei, " ", x, " ", y, "\n")

                x[argmin(y)]
            end


            x_min_clipped = max(x[1], min(x[end], x_min))
            print("fit ", i, " ", x, " ", y, " ", poly, " ", x_min, " ", x_min_clipped, "\n")

            # clip it within the fitting range
            push!(best_fit_value, x_min_clipped)
        end

        out[j] = (best_fit_value, minimum(chi2), flux, ivar, model_spectra[:, index...], convF .* convolved_inv_model_flux[:, index...])
        j += 1
    end
    out        
end

#=
     STUFF FOR LIVE SYNTHESIS
const synth_wls = ferre_wls[1] - 10 : 0.01 : ferre_wls[end] + 10
const LSF = Korg.compute_LSF_matrix(synth_wls, ferre_wls, 22_500)
const linelist = Korg.get_APOGEE_DR17_linelist();
const elements_to_fit = ["Mg", "Na", "Al"] # these are what will be fit
=#


end
