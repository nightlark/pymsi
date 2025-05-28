from pymsi import streamname
from pymsi.column import Column
from pymsi.reader import BinaryReader
from pymsi.stringpool import StringPool


class Table:
    def __init__(self, name: str, columns: list[Column]):
        self.name = name
        self.columns = columns
        self.rows = None

    def stream_name(self) -> str:
        return streamname.encode_unicode(self.name, True)

    def column_index(self, column_name: str) -> int | None:
        for index, column in enumerate(self.columns):
            if column.name == column_name:
                return index
        return None

    def column(self, column_name: str) -> Column | None:
        for column in self.columns:
            if column.name == column_name:
                return column
        return None

    def primary_key_indices(self) -> list[int]:
        return [index for index, column in enumerate(self.columns) if column.primary_key]

    def _read_rows(
        self, reader: BinaryReader, string_pool: StringPool, as_dict=True
    ) -> list[list] | list[dict]:
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

        if as_dict:
            return [dict(zip([col.name for col in self.columns], row)) for row in rows]
        return rows

    def read_rows(self, reader: BinaryReader, string_pool: StringPool) -> list[list] | list[dict]:
        if self.rows is None:
            self.rows = self._read_rows(reader, string_pool, True)
        return self.rows

    def __getitem__(self, row: int) -> dict:
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
