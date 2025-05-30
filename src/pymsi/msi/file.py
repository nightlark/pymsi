from typing import TYPE_CHECKING, Dict

from pymsi.thirdparty.refinery.cab import CabFile

if TYPE_CHECKING:
    from .component import Component
    from .media import Media


# https://learn.microsoft.com/en-us/windows/win32/msi/file-table
class File:
    def __init__(self, row: Dict):
        self.id: str = row["File"]
        self._component: str = row["Component_"]
        self.name: str = row["FileName"]
        self.size: int = row["FileSize"]
        self.version = row["Version"]
        langs = row["Language"]
        langs = langs.split(",") if isinstance(langs, str) else []
        self.language = [lang.strip() for lang in langs if lang.strip()]
        self.attributes: int = row["Attributes"]
        self.sequence: int = row["Sequence"]

    def resolve(self) -> CabFile:
        if not hasattr(self.media, "cabinet"):
            raise ValueError(
                f"Media for file {self.id} ({self.name}) is not resolved. Make sure load_data is set to True."
            )

        if self.media.cabinet is None:
            raise ValueError(
                f"Media for file {self.id} ({self.name}) does not have an associated .cab file."
            )

        for file in self.media.cabinet.get_files():
            if file.name == self.id:
                return file
        raise ValueError(f"File {self.name} not found in media cabinet {self.media.cabinet}.")

    def _populate(self, component_map: Dict[str, "Component"], media_map: Dict[int, "Media"]):
        self.component = component_map[self._component]
        self.component._add_file(self)

        self.media = min(
            [media for media in media_map.values() if media.last_sequence >= self.sequence],
            key=lambda m: m.last_sequence,
        )

    def pretty_print(self, indent: int = 0):
        print(" " * indent + f"File: {self.name} ({self.id})")
        print(" " * (indent + 2) + f"Size: {self.size} bytes")
        print(" " * (indent + 2) + f"Version: {self.version}")
        print(" " * (indent + 2) + f"Language(s): {', '.join(self.language)}")
        print(" " * (indent + 2) + f"Attributes: {hex(self.attributes)} ({self.attributes})")
        print(" " * (indent + 2) + f"Sequence: {self.sequence}")
        print(
            " " * (indent + 2) + f"Component: {self.component.id} ({self.component.directory.name})"
        )
        print(
            " " * (indent + 2)
            + f"Media: {self.media.id} (Last Sequence: {self.media.last_sequence})"
        )
        if hasattr(self.media, "cabinet") and self.media.cabinet is not None:
            file = self.resolve()
            print(" " * (indent + 2) + f"Cabinet Size: {file.size} bytes")
            if file.date is not None:
                print(" " * (indent + 2) + f"Cabinet Date: {file.date}")
            if file.time is not None:
                print(" " * (indent + 2) + f"Cabinet Time: {file.time}")
            print(
                " " * (indent + 2)
                + f"Cabinet Attributes: {hex(file.attributes)} ({file.attributes})"
            )
