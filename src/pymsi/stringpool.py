from typing import List, Tuple

from .codepage import CodePage
from .reader import BinaryReader

LONG_STRING_REFS_BIT = 0x8000_0000


class StringPool:
    def __init__(self, pool_stream, data_stream):
        pool_reader = BinaryReader(pool_stream)
        data_reader = BinaryReader(data_stream)

        codepage_id = pool_reader.read_u32_le()
        self.long_string_refs = (codepage_id & LONG_STRING_REFS_BIT) != 0
        codepage_id = codepage_id & ~LONG_STRING_REFS_BIT
        self.codepage = CodePage(codepage_id)

        self.strings: List[Tuple[str, int]] = []
        while not pool_reader.iseof():
            length = pool_reader.read_u16_le()
            refcount = pool_reader.read_u16_le()
            if length == 0 and refcount > 0:
                length = pool_reader.read_u32_le()
            self.strings.append((self.codepage.decode(data_reader.read_bytes(length)), refcount))

    def __getitem__(self, stringref: int):
        if 0 > stringref or stringref >= len(self.strings):
            raise IndexError("Index out of range")
        return self.strings[stringref][0]

    def refcount(self, stringref: int):
        if 0 > stringref or stringref >= len(self.strings):
            raise IndexError("Index out of range")
        return self.strings[stringref][1]

    def read_string(self, reader: BinaryReader):
        idx = reader.read_u16_le()
        if self.long_string_refs:
            idx = reader.read_u8() << 16 | idx
        if idx == 0:
            return None
        return self[idx - 1]
