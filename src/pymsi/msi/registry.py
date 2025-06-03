from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from .component import Component


# https://learn.microsoft.com/en-us/windows/win32/msi/registry-table
class Registry:
    def __init__(self, row: Dict):
        self.id: str = row["Registry"]
        root = row["Root"]
        if root == 0:
            self.root = "HKEY_CLASSES_ROOT"
        elif root == 1:
            self.root = "HKEY_CURRENT_USER"
        elif root == 2:
            self.root = "HKEY_LOCAL_MACHINE"
        elif root == 3:
            self.root = "HKEY_USERS"
        elif root == -1:
            self.root = None
        else:
            raise ValueError(f"Invalid registry root value: {root}")
        self.key: str = row["Key"]
        self.name: Optional[str] = row["Name"]
        # Value has unique parsing requirements, but I'm not doing that here
        self.value: Optional[str] = row["Value"]
        self._component: str = row["Component_"]

    def _populate(self, component_map: Dict[str, "Component"]):
        self.component = component_map[self._component]
        self.component._add_registry_key(self)

    def pretty_print(self, indent: int = 0):
        print(" " * indent + f"Registry Key: {self.id}")
        print(" " * (indent + 2) + f"Key: {self.root}\\{self.key}")
        if self.name is not None:
            print(" " * (indent + 2) + f"Name: {self.name}")
        if self.value is not None:
            print(" " * (indent + 2) + f"Value: {self.value}")
        print(
            " " * (indent + 2) + f"Component: {self.component.id} ({self.component.directory.name})"
        )
