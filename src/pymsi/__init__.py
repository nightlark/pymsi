try:
    from ._version import __version__, __version_tuple__
except ModuleNotFoundError:
    __version__ = ""
    __version_tuple__ = ()

from .pymsi import *  # noqa: F403
from .msi import * # noqa: F403
from .package import Package