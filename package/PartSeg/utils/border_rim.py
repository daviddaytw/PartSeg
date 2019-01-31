import SimpleITK as sitk
import numpy as np

from .universal_const import UNIT_SCALE, Units


def border_mask(mask: np.ndarray, distance: float, units: Units, voxel_size, **_):
    if mask is None:
        return None
    units_scalar = UNIT_SCALE[units.value]
    final_radius = [int((distance / units_scalar) / x) for x in voxel_size]
    mask = np.array(mask > 0)
    mask = mask.astype(np.uint8)
    eroded = sitk.GetArrayFromImage(sitk.BinaryErode(sitk.GetImageFromArray(mask), final_radius))
    mask[eroded > 0] = 0
    return mask
