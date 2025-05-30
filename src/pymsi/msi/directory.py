from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from .component import Component
    from .remove_file import RemoveFile
    from .shortcut import Shortcut


# https://learn.microsoft.com/en-us/windows/win32/msi/directory-table
class Directory:
    def __init__(self, row: Dict):
        self.id: str = row["Directory"]
        self._parent: str = row["Directory_Parent"]
        self.name: str = row["DefaultDir"]

        # DefaultDir can be in target:source format
        # Target is the actual install location, but files could be overlapped
        # If we decide to install all files
        if ":" in self.name:
            print(f"Warning: Directory has a target/source name: {self.name}")
            print("The directory structure may not be accurate.")
            target_dir, source_dir = self.name.split(":", 1)
            self.name = source_dir

        # Localize name
        if "|" in self.name:
            self.name = self.name.split("|", 1)[0]

        self.children: Dict[str, "Directory"] = {}
        self.components: Dict[str, "Component"] = {}
        self.shortcuts: Dict[str, "Shortcut"] = {}
        self.remove_files: Dict[str, "RemoveFile"] = {}

    def _add_child(self, child: "Directory"):
        self.children[child.id] = child

    def _add_component(self, component: "Component"):
        self.components[component.id] = component

    def _add_shortcut(self, shortcut: "Shortcut"):
        self.shortcuts[shortcut.id] = shortcut

    def _add_remove_file(self, remove_file: "RemoveFile"):
        self.remove_files[remove_file.id] = remove_file

    def _populate(self, directory_map: Dict[str, "Directory"]):
        if self._parent and self._parent != self.id:
            if self._parent not in directory_map:
                print(
                    f"Warning: Parent directory '{self._parent}' not found for directory '{self.id}'."
                )
                directory_map[self._parent] = Directory(
                    {"Directory": self._parent, "Directory_Parent": "TARGETDIR", "DefaultDir": "."}
                )

            self.parent = directory_map[self._parent]
            self.parent._add_child(self)
        else:
            self.parent = None

    def pretty_print(self, indent: int = 0):
        print(" " * indent + f"Directory: {self.name} ({self.id})")
        for component in self.components.values():
            component.pretty_print(indent + 4)
        for shortcut in self.shortcuts.values():
            shortcut.pretty_print(indent + 4)
        for remove_file in self.remove_files.values():
            remove_file.pretty_print(indent + 4)
        if len(self.children) > 0:
            print(" " * (indent + 2) + "Children:")
            for child in self.children.values():
                child.pretty_print(indent + 4)
