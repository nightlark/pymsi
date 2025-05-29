from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from .component import Component
    from .directory import Directory


# https://learn.microsoft.com/en-us/windows/win32/msi/removefile-table
class RemoveFile:
    def __init__(self, row: Dict):
        self.id: str = row["FileKey"]
        self._component: str = row["Component_"]
        self.name: Optional[str] = row["FileName"]
        # DirProperty points to either a Directory, an AppSearch row, or "any other property that represents a full path."
        self._dirproperty: str = row["DirProperty"]
        self.install_mode: int = row["InstallMode"]

    def _populate(
        self, component_map: Dict[str, "Component"], directory_map: Dict[str, "Directory"]
    ):
        self.component = component_map[self._component]
        self.component._add_remove_file(self)

        self.directory = directory_map.get(self._dirproperty)
        if self.directory is not None:
            self.directory._add_remove_file(self)

    def pretty_print(self, indent: int = 0):
        print(" " * indent + f"RemoveFile: {self.name} ({self.id})")
        print(
            " " * (indent + 2) + f"Component: {self.component.id} ({self.component.directory.name})"
        )
        if self.directory:
            print(" " * (indent + 2) + f"Directory: {self.directory.name} ({self.directory.id})")
        print(" " * (indent + 2) + f"Install Mode: {self.install_mode}")
