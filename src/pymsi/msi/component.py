from typing import Dict

from pymsi.msi.directory import Directory
from pymsi.msi.file import File
from pymsi.msi.registry import Registry
from pymsi.msi.remove_file import RemoveFile
from pymsi.msi.shortcut import Shortcut


# https://learn.microsoft.com/en-us/windows/win32/msi/component-table
class Component:
    def __init__(self, row: Dict):
        self.id: str = row["Component"]
        self.guid = row["ComponentId"]
        self._directory: str = row["Directory_"]
        self.attributes: int = row["Attributes"]
        self.condition: str = row["Condition"]
        self.key_path: str = row["KeyPath"]

        self.files: Dict[str, "File"] = {}
        self.shortcuts: Dict[str, "Shortcut"] = {}
        self.registry_keys: Dict[str, "Registry"] = {}
        self.remove_files: Dict[str, "RemoveFile"] = {}

    def _add_file(self, file: "File"):
        self.files[file.id] = file

    def _add_shortcut(self, shortcut: "Shortcut"):
        self.shortcuts[shortcut.id] = shortcut

    def _add_registry_key(self, registry: "Registry"):
        self.registry_keys[registry.id] = registry

    def _add_remove_file(self, remove_file: "RemoveFile"):
        self.remove_files[remove_file.id] = remove_file

    def _populate(self, directory_map: Dict[str, Directory]):
        self.directory = directory_map[self._directory]
        self.directory._add_component(self)

    def pretty_print(self, indent: int = 0):
        print(" " * indent + f"Component: {self.id} (GUID: {self.guid})")
        print(" " * (indent + 2) + f"Directory: {self.directory.name} ({self.directory.id})")
        print(" " * (indent + 2) + f"Attributes: {self.attributes}")
        print(" " * (indent + 2) + f"Condition: {self.condition}")
        print(" " * (indent + 2) + f"KeyPath: {self.key_path}")

        for file in self.files.values():
            file.pretty_print(indent + 4)

        for shortcut in self.shortcuts.values():
            shortcut.pretty_print(indent + 4)

        for registry in self.registry_keys.values():
            registry.pretty_print(indent + 4)

        for remove_file in self.remove_files.values():
            remove_file.pretty_print(indent + 4)
