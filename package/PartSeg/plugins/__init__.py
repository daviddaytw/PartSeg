import importlib
import itertools
import os
import pkgutil
import sys
import typing

import pkg_resources

import PartSegCore.plugins


def get_plugins():
    if getattr(sys, "frozen", False):
        new_path = [os.path.join(os.path.dirname(os.path.dirname(__path__[0])), "plugins")]
        packages = pkgutil.iter_modules(new_path, "plugins" + ".")
        import napari
        import napari_plugin_engine
        import napari_svg

        import PartSegCore.napari_plugin

        napari.plugins.plugin_manager.register(napari_svg)
        napari.plugins.plugin_manager.register(PartSegCore.napari_plugin)
        napari.plugins.plugin_manager.register(napari_plugin_engine)
    else:
        packages = pkgutil.iter_modules(__path__, __name__ + ".")
    packages2 = itertools.chain(
        pkg_resources.iter_entry_points("PartSeg.plugins"), pkg_resources.iter_entry_points("partseg.plugins"),
    )
    return [importlib.import_module(el.name) for el in packages] + [el.load() for el in packages2]


plugins_loaded = set()


def register():
    PartSegCore.plugins.register()
    for el in get_plugins():
        if hasattr(el, "register") and el.__name__ not in plugins_loaded:
            assert isinstance(el.register, typing.Callable)  # nosec
            el.register()
            plugins_loaded.add(el.__name__)
