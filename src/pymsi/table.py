import copy
from typing import Dict, List, Optional

from pymsi import streamname
from pymsi.column import Column
from pymsi.reader import BinaryReader
from pymsi.stringpool import StringPool


class Table:
    def __init__(self, name: str, columns: List[Column]):
        self.name = name
        self.columns = columns
        self.rows = None

    def stream_name(self) -> str:
        return streamname.encode_unicode(self.name, True)

    def column_index(self, column_name: str) -> Optional[int]:
        for index, column in enumerate(self.columns):
            if column.name == column_name:
                return index
        return None

    def column(self, column_name: str) -> Optional[Column]:
        for column in self.columns:
            if column.name == column_name:
                return column
        return None

    def primary_key_indices(self) -> List[int]:
        return [index for index, column in enumerate(self.columns) if column.primary_key]

    def _read_rows(self, reader: BinaryReader, string_pool: StringPool) -> List[Dict]:
        data_len = reader.size() - reader.tell()
        row_size = sum([c.width(string_pool.long_string_refs) for c in self.columns])
        num_rows = 0 if row_size == 0 else data_len // row_size
        if data_len % row_size != 0:
            raise ValueError("Data length is not a multiple of row size")
        if num_rows > 0x10_0000:
            raise ValueError("Too many rows in table, maximum is 65536")

        rows = [[] for _ in range(num_rows)]
        for col in self.columns:
            for row in range(num_rows):
                rows[row].append(col.read_value(reader, string_pool))

        rows = [dict(zip([col.name for col in self.columns], row)) for row in rows]
        return rows

    def read_rows(self, reader: Optional[BinaryReader], string_pool: StringPool) -> List[Dict]:
        if self.rows is None:
            if reader is None:
                self.rows = []
            else:
                self.rows = self._read_rows(reader, string_pool)
        return self.rows

    def get(self, row: int, localize: bool = False) -> Dict:
        if self.rows is None:
            raise ValueError("Rows not read yet, call read_rows() first")
        row_data = self.rows[row]
        if localize:
            row_data = copy.copy(row_data)
            for column in self.columns:
                if column.localizable:
                    row_data[column.name] = Column.localize(row_data[column.name])
        return row_data

    def iter(self, localize: bool = False):
        if self.rows is None:
            raise ValueError("Rows not read yet, call read_rows() first")
        if localize:
            return (self.get(row, localize=True) for row in range(len(self.rows)))
        return iter(self.rows)

    def __getitem__(self, row: int) -> Dict:
        if self.rows is None:
            raise ValueError("Rows not read yet, call read_rows() first")
        return self.rows[row]

    def __iter__(self):
        if self.rows is None:
            raise ValueError("Rows not read yet, call read_rows() first")
        return iter(self.rows)

    def __len__(self):
        if self.rows is None:
            raise ValueError("Rows not read yet, call read_rows() first")
        return len(self.rows)
