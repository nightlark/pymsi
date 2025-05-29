from typing import Dict, Optional


# https://learn.microsoft.com/en-us/windows/win32/msi/media-table
class Media:
    def __init__(self, row: Dict):
        self.id: int = row["DiskId"]
        self.last_sequence: int = row["LastSequence"]
        self.disk_prompt: Optional[str] = row["DiskPrompt"]
        self.cabinet: Optional[str] = row["Cabinet"]
        self.volume_label: Optional[str] = row["VolumeLabel"]
        self.source: Optional[str] = row["Source"]

    def pretty_print(self, indent: int = 0):
        print(" " * indent + f"Media: {self.id}")
        print(" " * (indent + 2) + f"Last Sequence: {self.last_sequence}")
        if self.disk_prompt:
            print(" " * (indent + 2) + f"Disk Prompt: {self.disk_prompt}")
        if self.cabinet:
            print(" " * (indent + 2) + f"Cabinet: {self.cabinet}")
        if self.volume_label:
            print(" " * (indent + 2) + f"Volume Label: {self.volume_label}")
        if self.source:
            print(" " * (indent + 2) + f"Source: {self.source}")
