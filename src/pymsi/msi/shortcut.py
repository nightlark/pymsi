from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from .component import Component
    from .directory import Directory
    from .icon import Icon


# https://learn.microsoft.com/en-us/windows/win32/msi/shortcut-table
class Shortcut:
    def __init__(self, row: Dict):
        self.id: str = row["Shortcut"]
        self._directory: str = row["Directory_"]
        self.name: str = row["Name"]
        self._component: str = row["Component_"]
        self.target: str = row["Target"]
        self.arguments: str = row["Arguments"]
        self.description: str = row["Description"]
        self.hotkey: str = row["Hotkey"]
        self._icon: str = row["Icon_"]
        self.icon_index: int = row["IconIndex"]
        self.show_command: int = row["ShowCmd"]
        self.working_directory: str = row["WkDir"]

    def _populate(
        self,
        directory_map: Dict[str, "Directory"],
        component_map: Dict[str, "Component"],
        icon_map: Dict[str, "Icon"],
    ):
        self.directory = directory_map[self._directory]
        self.directory._add_shortcut(self)

        self.component = component_map[self._component]
        self.component._add_shortcut(self)

        if self._icon:
            self.icon = icon_map[self._icon]
        else:
            self.icon = None

    def pretty_print(self, indent: int = 0):
        print(" " * indent + f"Shortcut: {self.name} ({self.id})")
        print(" " * (indent + 2) + f"Target: {self.target}")
        print(" " * (indent + 2) + f"Arguments: {self.arguments}")
        print(" " * (indent + 2) + f"Description: {self.description}")
        print(" " * (indent + 2) + f"Hotkey: {self.hotkey}")
        if self.icon:
            print(" " * (indent + 2) + f"Icon: {self.icon.id} ({self.icon.data})")
            print(" " * (indent + 2) + f"Icon Index: {self.icon_index}")
        else:
            print(" " * (indent + 2) + "Icon: None")
        print(" " * (indent + 2) + f"Show Command: {self.show_command}")
        print(" " * (indent + 2) + f"Working Directory: {self.working_directory}")
        print(
            " " * (indent + 2) + f"Component: {self.component.id} ({self.component.directory.name})"
        )
        if self.directory:
            print(" " * (indent + 2) + f"Directory: {self.directory.name} ({self.directory.id})")
