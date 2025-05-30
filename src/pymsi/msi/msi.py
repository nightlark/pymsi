from typing import Any, Dict, Optional, Type, TypeVar, Union

from pymsi import streamname
from pymsi.msi.component import Component
from pymsi.msi.directory import Directory
from pymsi.msi.file import File
from pymsi.msi.icon import Icon
from pymsi.msi.media import Media
from pymsi.msi.registry import Registry
from pymsi.msi.remove_file import RemoveFile
from pymsi.msi.shortcut import Shortcut
from pymsi.package import Package

T = TypeVar("T")


class Msi:
    def __init__(self, package: Package, load_data: bool = False):
        self.package = package

        self.components = self._load_map(Component, "Component")
        self.directories = self._load_map(Directory, "Directory")
        self.files = self._load_map(File, "File")
        self.icons = self._load_map(Icon, "Icon")
        self.registry_keys = self._load_map(Registry, "Registry")
        self.remove_files = self._load_map(RemoveFile, "RemoveFile")
        self.shortcuts = self._load_map(Shortcut, "Shortcut")
        self.medias = self._load_map(Media, "Media")

        if load_data:
            self._load_media()

        self._populate_map(self.components, self.directories)
        self._populate_map(self.directories, self.directories)
        self._populate_map(self.files, self.components, self.medias)
        self._populate_map(self.registry_keys, self.components)
        self._populate_map(self.remove_files, self.components, self.directories)
        self._populate_map(self.shortcuts, self.directories, self.components, self.icons)

        self.root = self._load_root()

    def _load_map(self, type_val: Type[T], name: str):
        table = self.package.get(name)
        ret: Union[Dict[str, T], Dict[int, T]] = {}
        if table is not None:
            for row in table.iter(True):
                val = type_val(row)
                ret[val.id] = val
        return ret

    @staticmethod
    def _populate_map(
        map: Optional[Union[Dict[str, T], Dict[int, T]]],
        *inputs: Union[Dict[str, Any], Dict[int, Any]],
    ):
        if map is None:
            return

        processed = set()
        while True:
            before_count = len(map)
            for key in list(map.keys()):
                if key not in processed:
                    map[key]._populate(*inputs)
                    processed.add(key)
            if len(map) == before_count:
                break

    def _load_media(self):
        for media in self.medias.values():
            if media._cabinet is None:
                media._populate(None)
            elif media._cabinet.startswith("#"):
                # Inside the .msi file
                stream_name = streamname.encode_unicode(media._cabinet[1:])
                if not self.package.ole.exists(stream_name):
                    raise ValueError(
                        f"Media file '{media._cabinet[1:]}' not found in the .msi file"
                    )
                with self.package.ole.openstream(stream_name) as stream:
                    media._populate(stream.read())
            else:
                # External cabinet file
                path = (self.package.path.parent / media._cabinet).resolve(True)
                # Check for path traversal attempts
                if self.package.path.parent not in path.parents:
                    raise ValueError(
                        f"Media file path '{media._cabinet}' attempts to access parent directories"
                    )

                if not path.is_file():
                    raise ValueError(f"External media file '{media._cabinet}' not found")
                with path.open("rb") as f:
                    media._populate(f.read())

    def _load_root(self):
        roots = [directory for directory in self.directories.values() if directory.parent is None]

        if len(roots) != 1:
            for root in roots:
                root.pretty_print()
            raise ValueError("There should be exactly one root directory in the file tree")

        return roots[0]

    def pretty_print(self):
        self.root.pretty_print()
        for media in self.medias.values():
            media.pretty_print()
