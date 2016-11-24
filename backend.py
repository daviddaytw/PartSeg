from __future__ import print_function, division
import matplotlib
from matplotlib import pyplot
import numpy as np
import SimpleITK as sitk
import h5py
import json
import tempfile
import os
import tarfile
import auto_fit as af
import logging
from enum import Enum
from copy import deepcopy
UPPER = "Upper"
GAUSS = "Gauss"


class MaskChange(Enum):
    prev_seg = 1
    next_seg = 2


def class_to_dict(obj, *args):
    """
    Create dict which contains values of given fields
    :type obj: object
    :type args: list[str]
    :return:
    """
    res = dict()
    for name in args:
        res[name] = getattr(obj, name)
    return res


def dict_set_class(obj, dic, *args):
    """
    Set fields of given object based on values from dict.
    If *args contains no names all values from dict are used
    :type obj: object
    :type dic: dict[str,object]
    :param args: list[str]
    :return:
    """
    if len(args) == 0:
        li = dic.keys()
    else:
        li = args
    for name in li:
        tt = getattr(obj, name)
        setattr(obj, name, dic[name])


def gaussian(image, radius):
    """
    :param image: image to apply gausian filter
    :param radius: radius for gaussian kernel
    :return:
    """
    if len(image.shape) == 2:
        return sitk.GetArrayFromImage(sitk.DiscreteGaussian(sitk.GetImageFromArray(image), radius))
    res = np.copy(image)
    for layer in res:
        layer[...] = sitk.GetArrayFromImage(sitk.DiscreteGaussian(sitk.GetImageFromArray(layer), radius))
    return res


def dilate(image, radius):
    """
    :param image: image to apply gausian filter
    :param radius: radius for gaussian kernel
    :return:
    """
    if len(image.shape) == 2:
        return sitk.GetArrayFromImage(sitk.GrayscaleDilate(sitk.GetImageFromArray(image), radius))
    res = np.copy(image)
    for layer in res:
        layer[...] = sitk.GetArrayFromImage(sitk.GrayscaleDilate(sitk.GetImageFromArray(layer), radius))
    return res


def to_binary_image(image):
    return np.array(image > 0).astype(np.uint8)


def bisect(arr, val, comp):
    l = -1
    r = len(arr)
    while r - l > 1:
        e = (l + r) >> 1
        if comp(arr[e], val): l = e
        else: r = e
    return r


class Profile:
    def __init__(self, name, threshold, threshold_list, threshold_type, minimum_size, use_gauss):
        """
        :param name: str,
        :param threshold: int
        :param threshold_list: list[int]
        :param threshold_type: str
        :param minimum_size: int
        :param use_gauss: bool
        """
        self.name = name
        self.threshold = threshold
        self.threshold_list = threshold_list
        self.threshold_type = threshold_type
        self.minimum_size = minimum_size
        self.use_gauss = use_gauss

    def __str__(self):
        text = self.name + "\n"

        return text


class Settings(object):
    """
    :type profiles: dict[str, Profile]
    :type threshold: int
    :type threshold_list: list[int]
    :type threshold_type: str
    :type minimum_size: int
    :type image: np.ndarray
    :type image_change_callback: list[() -> None]
    """
    def __init__(self, setings_path):
        self.color_map_name = "cubehelix"
        self.color_map = matplotlib.cm.get_cmap(self.color_map_name)
        self.callback_colormap = []
        self.callback_colormap_list = []
        self.callback_change_layer = []
        self.chosen_colormap = pyplot.colormaps()
        self.profiles = dict()
        self.use_gauss = False
        self.use_draw_result = False
        self.draw_callback = []
        self.threshold = 33000
        self.threshold_list = []
        self.threshold_type = UPPER
        self.threshold_layer_separate = False
        self.minimum_size = 100
        self.overlay = 0.7
        self.mask_overlay = 0.7
        self.power_norm = 1
        self.image = None
        self.gauss_image = None
        self.mask = None
        self.image_change_callback = []
        self.threshold_change_callback = []
        self.threshold_type_change_callback = []
        self.minimum_size_change_callback = []
        self.metadata_changed_callback = []
        self.layer_num = 0
        self.open_directory = None
        self.open_filter = None
        self.save_directory = None
        self.save_filter = None
        self.spacing = [5, 5, 30]
        self.voxel_size = [5, 5, 30]
        self.size_unit = "nm"
        self.advanced_menu_geometry = None
        self.file_path = ""
        self.protect = False
        self.load(setings_path)
        self.prev_segmentation_settings = []
        self.next_segmentation_settings = []
        self.mask_dilate_radius = 0

    def dump(self, file_path):
        important_data = \
            class_to_dict(self, "open_directory", "open_filter", "save_directory", "save_filter", "spacing",
                          "voxel_size", "size_unit", "threshold", "color_map_name", "overlay", "minimum_size")
        with open(file_path, "w") as ff:
            json.dump(important_data, ff)

    def load(self, file_path):
        try:
            with open(file_path, "r") as ff:
                important_data = json.load(ff)
            dict_set_class(self, important_data, "open_directory", "open_filter", "save_directory", "save_filter",
                           "spacing", "voxel_size", "size_unit", "threshold", "color_map_name", "overlay",
                           "minimum_size")
        except IOError:
            logging.warning("No configuration file")
            pass
        except KeyError:
            logging.warning("Bad configuration")

    def change_segmentation_mask(self, segment, order, save_draw):
        """
        :type segment: Segment
        :type order: MaskChange
        :type save_draw: bool
        :return:
        """
        save_fields = ["threshold", "threshold_list", "threshold_type", "threshold_layer_separate",
                       "minimum_size", "use_gauss", "use_draw_result", "mask_dilate_radius", "mask"]
        if order == MaskChange.prev_seg and len(self.prev_segmentation_settings) == 0:
            return

        current_mask = segment.get_segmentation()
        seg_settings = class_to_dict(self, *save_fields)
        seg_settings["draw_points"] = tuple(map(list, np.nonzero(np.array(segment.draw_canvas == 1))))
        seg_settings["erase_points"] = tuple(map(list, np.nonzero(np.array(segment.draw_canvas == 2))))
        save_draw_bck = np.copy(segment.draw_canvas)
        if order == MaskChange.next_seg:
            self.prev_segmentation_settings.append(seg_settings)
            if self.mask_dilate_radius > 0:
                self.mask = dilate(current_mask, self.mask_dilate_radius)
            else:
                self.mask = current_mask
            if len(self.next_segmentation_settings) > 0:
                new_seg = self.next_segmentation_settings.pop()
            else:
                new_seg = None
            save_fields = save_fields[:-1]
        else:
            self.next_segmentation_settings.append(seg_settings)
            new_seg = self.prev_segmentation_settings.pop()
        segment.draw_canvas[...] = 0
        if new_seg is not None:
            dict_set_class(self, new_seg, *save_fields)
            segment.draw_canvas[tuple(map(lambda x: np.array(x, dtype=np.uint32), new_seg["draw_points"]))] = 1
            segment.draw_canvas[tuple(map(lambda x: np.array(x, dtype=np.uint32), new_seg["erase_points"]))] = 2
        if save_draw:
            segment.draw_canvas[save_draw_bck > 0] = save_draw_bck[save_draw_bck > 0]
        for fun in self.threshold_change_callback:
            fun()
        for fun in self.callback_colormap:
            fun()
        self.advanced_settings_changed()

    def change_colormap(self, new_color_map=None):
        """
        :type new_color_map: str | none
        :param new_color_map: name of new colormap
        :return:
        """
        if new_color_map is not None:
            self.color_map_name = new_color_map
            self.color_map = matplotlib.cm.get_cmap(new_color_map)
        for fun in self.callback_colormap:
            fun()

    def add_colormap_list_callback(self, callback):
        self.callback_colormap_list.append(callback)

    def add_colormap_callback(self, callback):
        self.callback_colormap.append(callback)

    def remove_colormap_callback(self, callback):
        self.callback_colormap.remove(callback)

    def create_new_profile(self, name, overwrite=False):
        """
        :type name: str
        :type overwrite: bool
        :param name: Profile name
        :param overwrite: Overwrite existing profile
        :return:
        """
        if not overwrite and name in self.profiles:
            raise ValueError("Profile with this name already exists")
        self.profiles[name] = Profile(name, self.threshold, self.threshold_list, self.threshold_type, self.minimum_size)

    @property
    def colormap_list(self):
        return self.chosen_colormap

    @property
    def available_colormap_list(self):
        return pyplot.colormaps()

    def add_image(self, image, file_path, mask=None,):
        self.image = image
        self.gauss_image = gaussian(self.image, 1)
        self.mask = mask
        self.file_path = file_path
        self.threshold_list = []
        self.threshold_layer_separate = False
        for fun in self.image_change_callback:
            if isinstance(fun, tuple) and fun[1] == str:
                fun[0](file_path)
                continue
            if isinstance(fun, tuple) and fun[1] == GAUSS:
                fun[0](image, self.gauss_image)
                continue
            fun(image)

    def add_image_callback(self, callback):
        self.image_change_callback.append(callback)

    def change_threshold(self, new_threshold):
        if self.protect:
            return
        if self.threshold_layer_separate:
            if self.threshold_list[self.layer_num] == new_threshold:
                return
            self.threshold_list[self.layer_num] = new_threshold
        else:
            if self.threshold == new_threshold:
                return
            self.threshold = new_threshold
        for fun in self.threshold_change_callback:
            fun()

    def add_change_layer_callback(self, callback):
        self.callback_change_layer.append(callback)

    def change_layer(self, val):
        self.layer_num = val
        self.protect = True
        if self.threshold_layer_separate:
            for fun in self.callback_change_layer:
                fun(self.threshold_list[val])
        else:
            for fun in self.callback_change_layer:
                fun(self.threshold)
        # for fun in self.threshold_change_callback:
        #     fun()
        self.protect = False

    def change_threshold_type(self, new_type):
        print(new_type)
        if new_type == "Upper threshold:":
            self.threshold_type = UPPER
        else:
            self.threshold_type = "Lower"
        for fun in self.threshold_change_callback:
            fun()
        for fun in self.threshold_type_change_callback:
            fun()

    def change_layer_threshold(self, layer_threshold):
        self.threshold_layer_separate = layer_threshold
        if layer_threshold and self.threshold_list == []:
            self.threshold_list = [self.threshold] * self.image.shape[0]
        for fun in self.threshold_change_callback:
            fun()

    def change_gauss(self, use_gauss):
        self.use_gauss = bool(use_gauss)
        for fun in self.threshold_change_callback:
            fun()

    def add_threshold_callback(self, callback):
        self.threshold_change_callback.append(callback)

    def add_threshold_type_callback(self, callback):
        self.threshold_type_change_callback.append(callback)

    def change_min_size(self, new_min_size):
        self.minimum_size = new_min_size
        for fun in self.minimum_size_change_callback:
            fun()

    def add_min_size_callback(self, callback):
        self.minimum_size_change_callback.append(callback)

    def get_profile_list(self):
        return self.profiles.keys()

    def set_available_colormap(self, cmap_list):
        self.chosen_colormap = cmap_list
        for fun in self.callback_colormap_list:
            fun()

    def change_draw_use(self, use_draw):
        self.use_draw_result = use_draw
        for fun in self.draw_callback:
            fun()

    def add_draw_callback(self, callback):
        self.draw_callback.append(callback)

    def add_metadata_changed_callback(self, callback):
        self.metadata_changed_callback.append(callback)

    def advanced_settings_changed(self):
        for fun in self.threshold_type_change_callback:
            fun()
        for fun in self.metadata_changed_callback:
            fun()

    def metadata_changed(self):
        for fun in self.metadata_changed_callback:
            fun()


class Segment(object):
    """:type _segmented_image: np.ndarray"""
    def __init__(self, settings):
        """
        :type settings: Settings
        """
        self._settings = settings
        self._image = None
        self.draw_canvas = None
        self.draw_counter = 0
        self._gauss_image = None
        self._threshold_image = None
        self._segmented_image = None
        self._finally_segment = None
        self._sizes_array = []
        self.segmentation_change_callback = []
        self._segmentation_changed = True
        self.protect = False
        self._settings.add_threshold_callback(self.threshold_updated)
        self._settings.add_min_size_callback(self.min_size_updated)
        self._settings.add_draw_callback(self.draw_update)

    def set_image(self, image):
        self._image = image
        self._gauss_image = gaussian(self._image, 1)  # TODO radius in settings
        self._segmentation_changed = True
        self._finally_segment = np.zeros(image.shape, dtype=np.uint8)
        self.threshold_updated()

    def threshold_updated(self):
        if self.protect:
            return
        self._threshold_image = np.zeros(self._image.shape, dtype=np.uint8)
        if self._settings.use_gauss:
            image_to_threshold = self._gauss_image
        else:
            image_to_threshold = self._image
        # Define wich threshold use
        if self._settings.threshold_type == UPPER:
            def get_mask(image, threshold):
                return image <= threshold
        else:
            def get_mask(image, threshold):
                return image >= threshold

        if self._settings.threshold_layer_separate:
            print("Layer separate")
            for i in range(self._image.shape[0]):
                self._threshold_image[i][get_mask(image_to_threshold[i], self._settings.threshold_list[i])] = 1
        else:
            print("normal")
            self._threshold_image[get_mask(image_to_threshold, self._settings.threshold)] = 1
        if self._settings.mask is not None:
            self._threshold_image *= (self._settings.mask > 0)
        self.draw_update()

    def draw_update(self, canvas=None):
        if self.protect:
            return
        if canvas is not None:
            self.draw_canvas[...] = canvas[...]
            return
        if self._settings.use_draw_result:
            threshold_image = np.copy(self._threshold_image)
            threshold_image[self.draw_canvas == 1] = 1
            threshold_image[self.draw_canvas == 2] = 0
        else:
            threshold_image = self._threshold_image
        connect = sitk.ConnectedComponent(sitk.GetImageFromArray(threshold_image))
        self._segmented_image = sitk.GetArrayFromImage(sitk.RelabelComponent(connect))
        self._sizes_array = np.bincount(self._segmented_image.flat)
        self.min_size_updated()

    def min_size_updated(self):
        if self.protect:
            return
        ind = bisect(self._sizes_array[1:], self._settings.minimum_size, lambda x, y: x > y)
        # print(ind, self._sizes_array, self._settings.minimum_size)
        self._finally_segment = np.copy(self._segmented_image)
        self._finally_segment[self._finally_segment > ind] = 0
        self._segmentation_changed = True
        for fun in self.segmentation_change_callback:
            if isinstance(fun, tuple):
                fun[0](self._sizes_array[1:ind+1])
                continue
            fun()

    @property
    def segmentation_changed(self):
        """:rtype: bool"""
        return self._segmentation_changed

    def get_segmentation(self):
        self._segmentation_changed = False
        return self._finally_segment

    def get_size_array(self):
        return self._sizes_array

    def get_full_segmentation(self):
        return self._segmented_image

    def add_segmentation_callback(self, callback):
        self.segmentation_change_callback.append(callback)


def calculate_statistic_from_image(img, mask, settings):
    """
    :type img: np.ndarray
    :type mask: np.ndarray
    :type settings: Settings
    :return: dict[str,object]
    """
    def pixel_volume(x):
        return x[0] * x[1] * x[2]
    res = dict()
    voxel_size = settings.voxel_size
    res["Volume"] = np.count_nonzero(img) * pixel_volume(settings.voxel_size)
    res["Mass"] = np.sum(img)
    border_im = sitk.GetArrayFromImage(sitk.LabelContour(sitk.GetImageFromArray((mask > 0).astype(np.uint8))))
    res["Border Volume"] = np.count_nonzero(border_im)
    border_surface = 0
    surf_im = np.array((mask > 0)).astype(np.uint8)
    border_surface += np.count_nonzero(np.logical_xor(surf_im[1:], surf_im[:-1])) * voxel_size[1] * voxel_size[2]
    border_surface += np.count_nonzero(np.logical_xor(surf_im[:, 1:], surf_im[:, :-1])) * voxel_size[0] * \
                      voxel_size[2]
    if len(surf_im.shape) == 3:
        border_surface += np.count_nonzero(np.logical_xor(surf_im[:, :, 1:], surf_im[:, :, :-1])) * voxel_size[0] * \
                      voxel_size[1]
    res["Border Surface"] = border_surface
    res["Pixel min"] = np.min(img[img > 0])
    res["Pixel max"] = np.max(img)
    res["Pixel mean"] = np.mean(img[img > 0])
    res["Pixel median"] = np.median(img[img > 0])
    res["Pixel std"] = np.std(img[img > 0])
    if len(surf_im.shape) == 3:
        res["Moment of immersion"] = af.calculate_density_momentum(img / np.sum(img), voxel_size)

    return res


def get_segmented_data(settings, segment):
    segmentation = segment.get_segmentation()
    image = np.copy(settings.image)
    if settings.threshold_type == UPPER:
        full_segmentation = segment.get_full_segmentation()
        noise_mean = np.mean(image[full_segmentation == 0])
        image = noise_mean - image
    image[segmentation == 0] = 0  # min(image[segmentation > 0].min(), 0)
    image[image < 0] = 0
    return image, segmentation


def save_to_cmap(file_path, settings, segment, use_3d_gauss_filter=True, use_2d_gauss_filter=True, with_statistics=True,
                 centered_data=True):
    """
    :type file_path: str
    :type settings: Settings
    :type segment: Segment
    :type use_3d_gauss_filter: bool
    :type use_2d_gauss_filter: bool
    :type with_statistics: bool
    :type centered_data: bool
    :return:
    """

    image, mask = get_segmented_data(settings, segment)
    if use_2d_gauss_filter:
        image = gaussian(image, 1)
        image[mask == 0] = 0

    if use_3d_gauss_filter:
        voxel = settings.spacing
        sitk_image = sitk.GetImageFromArray(image)
        sitk_image.SetSpacing(settings.spacing)
        image = sitk.GetArrayFromImage(sitk.DiscreteGaussian(sitk_image, max(voxel)))
        image[mask == 0] = 0

    points = np.nonzero(image)
    lower_bound = np.min(points, axis=1)
    upper_bound = np.max(points, axis=1)
    print (image.shape, lower_bound, upper_bound, upper_bound-lower_bound)
    cut_img = np.zeros(upper_bound-lower_bound+[3, 11, 11], dtype=image.dtype)
    coord = []
    for l, u in zip(lower_bound, upper_bound):
        coord.append(slice(l, u))
    pos = tuple(coord)
    cut_img[1:-2, 5:-6, 5:-6] = image[pos]
    z, y, x = cut_img.shape
    f = h5py.File(file_path, "w")
    grp = f.create_group('Chimera/image1')
    dset = grp.create_dataset("data_zyx", (z, y, x), dtype='f')
    dset[...] = cut_img

    # Just to satisfy file format
    grp = f['Chimera']
    grp.attrs['CLASS'] = np.string_('GROUP')
    grp.attrs['TITLE'] = np.string_('')
    grp.attrs['VERSION'] = np.string_('1.0')

    grp = f['Chimera/image1']
    grp.attrs['CLASS'] = np.string_('GROUP')
    grp.attrs['TITLE'] = np.string_('')
    grp.attrs['VERSION'] = np.string_('1.0')
    grp.attrs['step'] = np.array(settings.spacing, dtype=np.float32)

    if centered_data:
        center_of_mass = af.density_mass_center(cut_img, settings.spacing)
        model_orientation, eigen_values = af.find_density_orientation(cut_img, settings.spacing, cutoff=2000)
        rotation_matrix, rotation_axis, angel = af.get_rotation_parameters(model_orientation.T)
        grp.attrs['rotation_axis'] = rotation_axis
        grp.attrs['rotation_angle'] = angel
        grp.attrs['origin'] = - np.dot(rotation_matrix, center_of_mass)

    dset.attrs['CLASS'] = np.string_('CARRY')
    dset.attrs['TITLE'] = np.string_('')
    dset.attrs['VERSION'] = np.string_('1.0')
    if with_statistics:
        grp = f.create_group('Chimera/image1/Statistics')
        stat = calculate_statistic_from_image(cut_img, segment.get_segmentation(), settings)
        for key, val in stat.items():
            grp.attrs[key] = val
    f.close()


def save_to_project(file_path, settings, segment):
    """
    :type file_path: str
    :type settings: Settings
    :type segment: Segment
    :return:
    """
    folder_path = tempfile.mkdtemp()
    np.save(os.path.join(folder_path, "image.npy"), settings.image)
    np.save(os.path.join(folder_path, "draw.npy"), segment.draw_canvas)
    np.save(os.path.join(folder_path, "res_mask.npy"), segment.get_segmentation())
    if settings.mask is not None:
        np.save(os.path.join(folder_path, "mask.npy"), settings.mask)
    important_data = class_to_dict(settings, 'threshold_type', 'threshold_layer_separate', "threshold", "threshold_list",
                                   'use_gauss', 'spacing', 'minimum_size', 'use_draw_result', "prev_segmentation_settings")
    important_data["prev_segmentation_settings"] = deepcopy(important_data["prev_segmentation_settings"])
    for c, mem in enumerate(important_data["prev_segmentation_settings"]):
        np.save(os.path.join(folder_path, "mask_{}.npy".format(c)), mem["mask"])
        del mem["mask"]
    image, segment_mask = get_segmented_data(settings, segment)
    important_data["statistics"] = calculate_statistic_from_image(image, segment_mask, settings)
    print(important_data)
    with open(os.path.join(folder_path, "data.json"), 'w') as ff:
        json.dump(important_data, ff)
    """if file_path[-3:] != ".gz":
        file_path += ".gz" """
    tar = tarfile.open(file_path, 'w:bz2')
    for name in os.listdir(folder_path):
        tar.add(os.path.join(folder_path, name), name)
    tar.close()


def load_project(file_path, settings, segment):
    """
    :type file_path: str
    :type settings: Settings
    :type segment: Segment
    :return:
    """
    tar = tarfile.open(file_path, 'r:bz2')
    members = tar.getnames()
    important_data = json.load(tar.extractfile("data.json"))
    image = np.load(tar.extractfile("image.npy"))
    draw = np.load(tar.extractfile("draw.npy"))
    if "mask.npy" in members:
        mask = np.load(tar.extractfile("mask.npy"))
    else:
        mask = None
    settings.threshold = int(important_data["threshold"])

    settings.threshold_type = important_data["threshold_type"]
    settings.use_gauss = bool(important_data["use_gauss"])
    settings.spacing = \
        tuple(map(int, important_data["spacing"]))
    settings.voxel_size = settings.spacing
    settings.minimum_size = int(important_data["minimum_size"])
    try:
        if "use_draw_result" in important_data:
            settings.use_draw_result = int(important_data["use_draw_result"])
        else:
            settings.use_draw_result = int(important_data["use_draw"])
    except KeyError:
        settings.use_draw_result = False
    segment.protect = True
    settings.add_image(image, file_path, mask)
    segment.protect = False
    if important_data["threshold_list"] is not None:
        settings.threshold_list = map(int, important_data["threshold_list"])
    else:
        settings.threshold_list = []
    if "threshold_layer_separate" in important_data:
        settings.threshold_layer_separate = \
            bool(important_data["threshold_layer_separate"])
    else:
        settings.threshold_layer_separate = \
            bool(important_data["threshold_layer"])

    if "prev_segmentation_settings" in important_data:
        for c, mem in enumerate(important_data["prev_segmentation_settings"]):
            mem["mask"] = np.load(tar.extractfile("mask_{}.npy".format(c)))
    print(settings.threshold_list)
    segment.draw_update(draw)
    segment.threshold_updated()
