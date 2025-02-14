"""
This module contains roi_extraction algorithms
"""

import os
import sys

from PartSegCore.segmentation.algorithm_base import ROIExtractionAlgorithm, ROIExtractionResult
from PartSegCore.segmentation.noise_filtering import NoiseFilteringBase
from PartSegCore.segmentation.restartable_segmentation_algorithms import RestartableAlgorithm
from PartSegCore.segmentation.segmentation_algorithm import StackAlgorithm
from PartSegCore.segmentation.threshold import BaseThreshold
from PartSegCore.segmentation.watershed import BaseWatershed

__all__ = [
    "BaseThreshold",
    "BaseWatershed",
    "NoiseFilteringBase",
    "ROIExtractionAlgorithm",
    "ROIExtractionResult",
    "RestartableAlgorithm",
    "StackAlgorithm",
]


if os.path.basename(sys.argv[0]) in ["sphinx-build", "sphinx-build.exe"]:
    for el in __all__:
        globals()[el].__module__ = __name__
