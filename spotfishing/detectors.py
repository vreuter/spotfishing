"""Different spot detection implementations"""

from typing import Optional, Tuple, Union

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import ndimage as ndi
from skimage.filters import gaussian  # type: ignore[import-untyped]
from skimage.measure import regionprops_table
from skimage.morphology import ball, remove_small_objects, white_tophat
from skimage.segmentation import expand_labels  # type: ignore[import-untyped]

from ._constants import *
from ._exceptions import DimensionalityError
from ._numeric_types import *
from .detection_result import (
    ROI_CENTROID_COLUMN_RENAMING,
    ROI_MEASUREMENT_KEYS,
    SKIMAGE_REGIONPROPS_TABLE_COLUMNS_EXPANDED,
    DetectionResult,
)

__author__ = "Vince Reuter"
__credits__ = ["Vince Reuter", "Kai Sandoval Beckwith"]

__all__ = ["detect_spots_dog", "detect_spots_int"]

Numeric = Union[int, float]


def detect_spots_dog(
    *,
    input_image: npt.NDArray[PixelValue],
    spot_threshold: Numeric,
    expand_px: Optional[Numeric],
) -> DetectionResult:
    """Spot detection by difference of Gaussians filter

    Arguments
    ---------
    input_image : ndarray
        3D image in which to detect spots
    spot_threshold : int or float
        Minimum peak value after the DoG transformation to call a peak/spot
    expand_px : float or int or NoneType
        Number of pixels by which to expand contiguous subregion,
        up to point of overlap with neighboring subregion of image

    Returns
    -------
    spotfishing.DetectionResult
        Bundle of table of ROI coordinates and data, the image used for spot detection, and region labels array
    """
    _check_input_image(input_image)
    img = _preprocess_for_difference_of_gaussians(input_image)
    labels, _ = ndi.label(img > spot_threshold)  # type: ignore[no-untyped-call]
    spot_props, labels = _build_props_table(
        labels=labels, input_image=input_image, expand_px=expand_px
    )
    return DetectionResult(table=spot_props, image=img, labels=labels)


def detect_spots_int(
    *,
    input_image: npt.NDArray[PixelValue],
    spot_threshold: Numeric,
    expand_px: Optional[Numeric],
) -> DetectionResult:
    """Spot detection by intensity filter

    Arguments
    ---------
    input_image : ndarray
        3D image in which to detect spots
    spot_threshold : NumberLike
        Minimum intensity value in a pixel to consider it as part of a spot region
    expand_px : float or int or NoneType
        Number of pixels by which to expand contiguous subregion,
        up to point of overlap with neighboring subregion of image

    Returns
    -------
    spotfishing.DetectionResult
        Bundle of table of ROI coordinates and data, the image used for spot detection, and region labels array
    """
    # TODO: enforce that output column names don't vary with code path walked.
    # See: https://github.com/gerlichlab/looptrace/issues/125
    _check_input_image(input_image)
    binary = input_image > spot_threshold
    binary = ndi.binary_fill_holes(binary)  # type: ignore[no-untyped-call]
    struct = ndi.generate_binary_structure(input_image.ndim, 2)  # type: ignore[no-untyped-call]
    labels, num_obj = ndi.label(binary, structure=struct)  # type: ignore[no-untyped-call]
    if num_obj > 1:
        labels = remove_small_objects(labels, min_size=5)
    spot_props, labels = _build_props_table(
        labels=labels, input_image=input_image, expand_px=expand_px
    )
    return DetectionResult(table=spot_props, image=input_image, labels=labels)


def _build_props_table(
    *,
    labels: npt.NDArray[NumpyInt],
    input_image: npt.NDArray[PixelValue],
    expand_px: Optional[Numeric],
) -> Tuple[pd.DataFrame, npt.NDArray[NumpyInt]]:
    if expand_px:
        labels = expand_labels(labels, expand_px)
    if np.all(labels == 0):
        # No substructures (ROIs) exist.
        spot_props = pd.DataFrame(columns=SKIMAGE_REGIONPROPS_TABLE_COLUMNS_EXPANDED)
    else:
        spot_props = pd.DataFrame(
            regionprops_table(
                label_image=labels,
                intensity_image=input_image,
                properties=tuple(
                    [ROI_LABEL_KEY, ROI_CENTROID_KEY] + ROI_MEASUREMENT_KEYS
                ),
            )
        )
    spot_props = spot_props.drop(["label"], axis=1, errors="ignore")
    spot_props = spot_props.rename(columns=dict(ROI_CENTROID_COLUMN_RENAMING))
    spot_props = spot_props.reset_index(drop=True)
    return spot_props, labels


def _check_input_image(img: npt.NDArray[PixelValue]) -> None:
    if not isinstance(img, np.ndarray):
        raise TypeError(
            f"Expected numpy array for input image but got {type(img).__name__}"
        )
    if img.ndim != 3:
        raise DimensionalityError(
            f"Expected 3D input image but got {img.ndim}-dimensional"
        )


def _preprocess_for_difference_of_gaussians(
    input_image: npt.NDArray[PixelValue],
) -> npt.NDArray[PixelValue]:
    img = white_tophat(image=input_image, footprint=ball(2))
    img = gaussian(img, 0.8) - gaussian(img, 1.3)
    img = img / gaussian(input_image, 3)
    img = (img - np.mean(img)) / np.std(img)
    return img  # type: ignore[no-any-return]
