from typing import Dict


# https://learn.microsoft.com/en-us/windows/win32/msi/icon-table
class Icon:
    def __init__(self, row: Dict):
        self.id: str = row["Name"]
        self.data = row["Data"]
