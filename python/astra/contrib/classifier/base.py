import numpy as np
from scipy import optimize as op
from scipy.special import logsumexp
from typing import Iterable
from astra.database.astradb import DataProduct, SDSSOutput
from astra.base import task_decorator
from astra.utils import log, expand_path, flatten
from astra.contrib.classifier.utils import read_network
from astra.contrib.classifier import networks
from astra.tools.spectrum import Spectrum1D
from functools import cache
from peewee import BooleanField, FloatField

import torch

SMALL = -1e+20

CUDA_AVAILABLE = torch.cuda.is_available()
DEVICE = torch.device("cuda:0") if CUDA_AVAILABLE else torch.device("cpu")


class ClassifierOutput(SDSSOutput):

    dithered = BooleanField(null=True)

    p_cv = FloatField(default=0)
    lp_cv = FloatField(default=SMALL)
    p_fgkm = FloatField(default=0)
    lp_fgkm = FloatField(default=SMALL)
    p_hotstar = FloatField(default=0)
    lp_hotstar = FloatField(default=SMALL)
    p_wd = FloatField(default=0)
    lp_wd = FloatField(default=SMALL)
    p_sb2 = FloatField(default=0)
    lp_sb2 = FloatField(default=SMALL)
    p_yso = FloatField(default=0)
    lp_yso = FloatField(default=SMALL)


@cache
def read_model(model_path):
    model_path = expand_path(model_path)
    factory = getattr(networks, model_path.split("_")[-2])
    model = read_network(factory, model_path)
    model.to(DEVICE)
    model.eval()
    return model


def classify_all_apVisit():
    q = (
        DataProduct
        .select()
        .where(DataProduct.filetype == "apVisit")
    )
    r = list(classify_apVisit(q))

def classify_all_specFull():
    q = (
        DataProduct
        .select()
        .where(DataProduct.filetype == "specFull")
    )
    r = list(classify_specFull(q))



@task_decorator
def classify_apVisit(
    data_product: Iterable[DataProduct],
    model_path: str = "$MWM_ASTRA/component_data/classifier/classifier_NIRCNN_77804646.pt",
) -> Iterable[ClassifierOutput]:

    expected_shape = (3, 4096)

    model = read_model(model_path)
    for data_product in data_product:
        assert data_product.filetype.lower() == "apvisit"

        try:
            spectrum = Spectrum1D.read(data_product.path)
        except:
            log.exception(f"Exception on data product {data_product} ")
            continue

        dithered = (spectrum.flux.size == np.prod(expected_shape))
        if dithered:
            flux = spectrum.flux.reshape(expected_shape)
        else:
            existing_flux = spectrum.flux.reshape((3, -1))
            flux = np.empty(expected_shape)
            for j in range(3):
                flux[j, ::2] = existing_flux[j]
                flux[j, 1::2] = existing_flux[j]
            
        
        continuum = np.nanmedian(flux, axis=1)
        batch = flux / continuum.reshape((-1, 1))
        batch = batch.reshape((-1, *expected_shape)).astype(np.float32)
        batch = torch.from_numpy(batch).to(DEVICE)

        log.info(f"Making predictions")
        with torch.no_grad():
            prediction = model.forward(batch)

        # Should be only one result with apVisit, but whatever..
        for log_probs in prediction.cpu().numpy():
            result = classification_result(log_probs, model.class_names)
            yield ClassifierOutput(
                data_product=data_product,
                spectrum=spectrum,
                dithered=dithered,
                **result
            )


@task_decorator
def classify_specFull(
    data_product: Iterable[DataProduct],
    model_path: str = "$MWM_ASTRA/component_data/classifier/classifier_OpticalCNN_40bb9164.pt",
) -> Iterable[ClassifierOutput]:

    model = read_model(model_path)
    si, ei = (0, 3800)  # MAGIC: same done in training

    for data_product in data_product:
        assert data_product.filetype.lower() == "specfull"

        try:
            spectrum = Spectrum1D.read(data_product.path)
        except:
            log.exception(f"Exception on data product {data_product} ")
            continue

        flux = spectrum.flux[si:ei]
        continuum = np.nanmedian(flux)
        batch = flux / continuum
        # remove nans
        finite = np.isfinite(batch)
        if not any(finite):
            log.warning(f"Skipping {data_product} because all values are NaN")
            continue
        
        if any(~finite):
            batch[~finite] = np.interp(
                spectrum.wavelength.value[si:ei][~finite],
                spectrum.wavelength.value[si:ei][finite],
                batch[finite],
            )        
        batch = batch.reshape((1, 1, -1)).astype(np.float32)
        batch = torch.from_numpy(batch).to(DEVICE)

        log.info(f"Making predictions")
        with torch.no_grad():
            prediction = model.forward(batch)

        # Should be only one result with specFull, but whatever..
        for log_probs in prediction.cpu().numpy():
            result = classification_result(log_probs, model.class_names)
            yield ClassifierOutput(
                data_product=data_product,
                spectrum=spectrum,
                **result
            )

   

@task_decorator
def classify_source(source_id: int) -> ClassifierOutput:

    q = (
        ClassifierOutput
        .select()
        .where(
            (ClassifierOutput.source_id == source_id)
        &   ClassifierOutput.data_product.is_null(False)
        )
    )
    log_probs = sum_log_probs(q)
    result = classification_result(log_probs)

    # TODO: not yet tested..
    foo = ClassifierOutput(
        source_id=source_id,
        **result
    )
    raise a


def sum_log_probs(iterable):
    log_probs = {}
    for result in iterable:
        for attr in result._meta.fields.keys():
            if attr.startswith("lp_"):
                name = attr[3:]
                log_probs.setdefault(name, 0)
                value = getattr(result, attr)
                if np.isfinite(value):
                    log_probs[name] += value
    return log_probs



def classification_result(log_probs, class_names=None, decimals=30):

    if class_names is None:
        if not isinstance(log_probs, dict):
            raise TypeError(
                f"If class_names is None then log_probs must be a dictionary"
            )
        class_names, log_probs = zip(*log_probs.items())

    log_probs = np.array(log_probs).flatten()
    # Calculate normalized probabilities.
    with np.errstate(under="ignore"):
        relative_log_probs = log_probs - logsumexp(log_probs)#, axis=1)[:, None]

    # Round for PostgreSQL 'real' type.
    # https://www.postgresql.org/docs/9.1/datatype-numeric.html
    # and
    # https://stackoverflow.com/questions/9556586/floating-point-numbers-of-python-float-and-postgresql-double-precision
    probs = np.round(np.exp(relative_log_probs), decimals)
    log_probs = np.round(log_probs, decimals)

    result = {f"p_{cn}": p for cn, p in zip(class_names, probs.T)}
    result.update({f"lp_{cn}": p for cn, p in zip(class_names, log_probs.T)})
    return result
