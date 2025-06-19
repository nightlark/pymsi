import copy
import io
from pathlib import Path
from typing import Iterator, Optional, Union

import olefile

from pymsi import streamname
from pymsi.category import CATEGORIES_ALL
from pymsi.column import Column
from pymsi.constants import STRING_DATA_TABLE_NAME, STRING_POOL_TABLE_NAME, SUMMARY_INFO_STREAM_NAME
from pymsi.reader import BinaryReader
from pymsi.table import Table
from pymsi.tables import TABLE_COLUMNS, TABLE_TABLES, TABLE_VALIDATION

from .stringpool import StringPool
from .summary import Summary


class Package:
    def __init__(self, path_or_bytesio: Union[Path, io.BytesIO]):
        if isinstance(path_or_bytesio, io.BytesIO):
            self.path = None
            self.file = path_or_bytesio
        else:
            self.path = path_or_bytesio.resolve(True)
            self.file = self.path.open("rb")
        self.tables = {}
        self.ole = None
        self.summary = None
        self._load()

    def _load(self):
        self.ole = olefile.OleFileIO(self.file)

        with self.ole.openstream(SUMMARY_INFO_STREAM_NAME) as stream:
            self.summary = Summary(stream)

        with self.ole.openstream(
            streamname.encode_unicode(STRING_POOL_TABLE_NAME, True)
        ) as pool_stream:
            with self.ole.openstream(
                streamname.encode_unicode(STRING_DATA_TABLE_NAME, True)
            ) as data_stream:
                self.string_pool = StringPool(pool_stream, data_stream)

        with self.ole.openstream(TABLE_TABLES.stream_name()) as stream:
            rows = TABLE_TABLES._read_rows(BinaryReader(stream), self.string_pool)
            table_names = {row["Name"] for row in rows}

        columns = self._read_columns()
        self.tables = {name: Table(name, columns[name]) for name in table_names}
        self._read_validations()
        self.tables[TABLE_TABLES.name] = copy.copy(TABLE_TABLES)
        self.tables[TABLE_COLUMNS.name] = copy.copy(TABLE_COLUMNS)

    def _read_columns(self):
        columns = {}
        with self.ole.openstream(TABLE_COLUMNS.stream_name()) as stream:
            rows = TABLE_COLUMNS._read_rows(BinaryReader(stream), self.string_pool)

            for row in rows:
                table_name = row["Table"]
                column_name = row["Name"]
                column_typebits = row["Type"]
                column_number = row["Number"]

                if table_name not in columns:
                    columns[table_name] = []
                columns[table_name].append((column_number, Column(column_name, column_typebits)))

        columns = dict(
            (name, [col[1] for col in sorted(cols, key=lambda x: x[0])])
            for name, cols in columns.items()
        )
        return columns

    def _read_validations(self):
        if not self.ole.exists(TABLE_VALIDATION.stream_name()):
            return

        nonexistent_tables = set()
        with self.ole.openstream(TABLE_VALIDATION.stream_name()) as stream:
            rows = TABLE_VALIDATION._read_rows(BinaryReader(stream), self.string_pool)
            for row in rows:
                table_name = row["Table"]
                column_name = row["Column"]
                is_nullable = row["Nullable"] == "Y"
                min_value = row["MinValue"]
                max_value = row["MaxValue"]
                key_table = row["KeyTable"]
                key_column = row["KeyColumn"]
                category = row["Category"]
                set_name = row["Set"]
                description = row["Description"]

                if table_name not in self.tables:
                    if table_name not in nonexistent_tables:
                        print(
                            f"Warning: Table {table_name} not found in package, skipping validation"
                        )
                        nonexistent_tables.add(table_name)
                    continue

                column = self.tables[table_name].column(column_name)
                if column is None:
                    print(
                        f"Warning: Column {column_name} not found in table {table_name}, skipping validation"
                    )
                    continue
                if is_nullable:
                    column.mark_nullable()
                if min_value is not None and max_value is not None:
                    column.mark_range(min_value, max_value)
                if key_table is not None and key_column is not None:
                    column.mark_foreign_key(key_table, key_column)
                if category is not None and category in CATEGORIES_ALL:
                    column.mark_category(category)
                if set_name is not None:
                    column.mark_enum_values(set_name.split(";"))
                if description is not None:
                    column.mark_description(description)

    def get(self, name: str) -> Optional[Table]:
        if name not in self.tables:
            return None

        table = self.tables[name]
        if table.rows is None:
            stream_name = table.stream_name()
            if self.ole.exists(stream_name):
                with self.ole.openstream(table.stream_name()) as stream:
                    reader = BinaryReader(stream)
                    table.read_rows(reader, self.string_pool)
            else:
                # Stream does not exist
                table.read_rows(None, self.string_pool)
        return table

    def __getitem__(self, name: str) -> Table:
        table = self.get(name)
        if table is None:
            raise KeyError(f"Table '{name}' not found in package")
        return table

    def __contains__(self, name: str) -> bool:
        return name in self.tables

    def __iter__(self) -> Iterator[Table]:
        return iter(self.tables.values())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self.file and hasattr(self.file, "close"):
            self.file.close()
