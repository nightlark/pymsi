from typing import Dict, Optional


# https://learn.microsoft.com/en-us/windows/win32/msi/icon-table
class Icon:
    def __init__(self, row: Dict):
        self.id: str = row["Name"]
        # Msi populates the external OBJECT stream when load_data=True.
        self.data: Optional[bytes] = None

    def _populate(self, data: bytes):
        self.data = data
