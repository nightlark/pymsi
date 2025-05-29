from typing import Optional

from pymsi.constants import (
    COL_FIELD_SIZE_MASK,
    COL_LOCALIZABLE_BIT,
    COL_NULLABLE_BIT,
    COL_PRIMARY_KEY_BIT,
    COL_STRING_BIT,
)
from pymsi.reader import BinaryReader
from pymsi.stringpool import StringPool


class Column:
    def __init__(self, name: str, bits: Optional[int] = None):
        self.name = name
        self.localizable = False
        self.nullable = False
        self.primary_key = False
        self.value_range_min = None
        self.value_range_max = None
        self.foreign_key_table = None
        self.foreign_key_index = None
        self.category = None
        self.enum_values = []
        self.description = None

        if bits:
            self.set_bits(bits)

    @staticmethod
    def localize(value: str) -> str:
        if value and "|" in value:
            return value.split("|", 1)[1]
        return value

    def set_bits(self, bits: int):
        field_size = bits & COL_FIELD_SIZE_MASK
        if bits & COL_STRING_BIT:
            self.string(field_size)
        elif field_size == 4:
            self.i32()
        #                       https://github.com/mdsteele/rust-msi/blob/800e689f12949518a2e4e7c2f51fe9dce1d5ed23/src/internal/column.rs#L47-L49
        elif field_size == 2 or field_size == 1:
            self.i16()
        else:
            raise ValueError(f"Invalid column field size: {field_size}")

        if bits & COL_LOCALIZABLE_BIT:
            self.localizable = True
        if bits & COL_NULLABLE_BIT:
            self.nullable = True
        if bits & COL_PRIMARY_KEY_BIT:
            self.primary_key = True

    def width(self, long_string_refs: bool):
        if self.type == "str":
            return 3 if long_string_refs else 2
        return self.size

    def read_value(self, reader: BinaryReader, string_pool: StringPool):
        if self.type == "str":
            return string_pool.read_string(reader)
        elif self.type == "i32":
            val = reader.read_i32_le()
            if val == 0:
                return None
            return val ^ -0x8000_0000
        elif self.type == "i16":
            val = reader.read_i16_le()
            if val == 0:
                return None
            return val ^ -0x8000
        else:
            raise ValueError(f"Unknown column type: {self.type}")

    def mark_primary_key(self):
        self.primary_key = True
        return self

    def mark_nullable(self):
        self.nullable = True
        return self

    def mark_range(self, min, max):
        self.value_range_min = min
        self.value_range_max = max
        return self

    def mark_foreign_key(self, table, index):
        self.foreign_key_table = table
        self.foreign_key_index = index
        return self

    def mark_enum_values(self, values):
        self.enum_values = values
        return self

    def mark_category(self, category):
        self.category = category
        return self

    def mark_description(self, description):
        self.description = description
        return self

    def string(self, size):
        self.type = "str"
        self.size = size
        return self

    def i32(self):
        self.type = "i32"
        self.size = 4
        return self

    def i16(self):
        self.type = "i16"
        self.size = 2
        return self

    def __str__(self):
        ret = f"Column({repr(self.name)}, {self.type}"
        if self.localizable:
            ret += ", localizable"
        if self.nullable:
            ret += ", nullable"
        if self.primary_key:
            ret += ", primary_key"
        if self.value_range_min is not None and self.value_range_max is not None:
            ret += f", value_range=({self.value_range_min}, {self.value_range_max})"
        if self.foreign_key_table is not None and self.foreign_key_index is not None:
            ret += f", foreign_key={self.foreign_key_table}.{self.foreign_key_index}"
        if self.category is not None:
            ret += f", category={self.category}"
        if self.enum_values:
            ret += f", enum_values={self.enum_values}"
        if self.description is not None:
            ret += f", description={repr(self.description)}"
        ret += ")"
        return ret
