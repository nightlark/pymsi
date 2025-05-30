from typing import Dict

from pymsi.constants import BOM, PROPERTY_CODEPAGE

from .codepage import CodePage
from .reader import BinaryReader
from .timestamp import to_datetime


class PropertySet:
    def __init__(self, stream):
        reader = BinaryReader(stream)
        bom = reader.read_u16_le()
        if bom != BOM:
            raise ValueError(f"Invalid BOM: expected {BOM}, got {bom}")

        file_version = reader.read_u16_le()
        if file_version not in [0, 1]:
            raise ValueError(f"Unsupported file version: {file_version}")

        self.os_version = reader.read_u16_le()
        self.os = reader.read_u16_le()
        if self.os not in [0, 1, 2]:
            raise ValueError(f"Unsupported OS: {self.os}")

        self.clsid = reader.read_bytes(16)

        if reader.read_u32_le() < 1:
            raise ValueError("Invalid reserved field")

        # Section header
        self.fmtid = reader.read_bytes(16)
        section_offset = reader.read_u32_le()

        # Section
        reader.seek(section_offset)
        section_size = reader.read_u32_le()
        num_props = reader.read_u32_le()
        prop_offsets = {}
        for _ in range(num_props):
            name = reader.read_u32_le()
            offset = reader.read_u32_le()
            if name in prop_offsets:
                raise ValueError(f"Duplicate property name: {name}")
            prop_offsets[name] = offset

        if PROPERTY_CODEPAGE in prop_offsets:
            codepage_offset = prop_offsets[PROPERTY_CODEPAGE]
            reader.seek(section_offset + codepage_offset)
            value = PropertyValue(reader, CodePage.DEFAULT)
            if not isinstance(value.value, int):
                raise ValueError(f"Invalid codepage value: {value.value} {type(value.value)}")
            self.codepage = CodePage(value.value)
        else:
            self.codepage = CodePage.DEFAULT

        self.properties: Dict[int, PropertyValue] = {}
        for name, offset in prop_offsets.items():
            reader.seek(section_offset + offset)
            value = PropertyValue(reader, self.codepage)
            if value.min_version > file_version:
                raise ValueError(
                    f"Property {name} ({value.type}) version {value.min_version} is not supported by file version {file_version}"
                )
            self.properties[name] = value

    def get(self, name: int):
        prop = self.properties.get(name)
        if prop is not None:
            return prop.value
        return None

    def __getitem__(self, name: int):
        return self.properties[name].value

    def __contains__(self, name: int) -> bool:
        return name in self.properties


class PropertyValue:
    def __init__(self, reader: BinaryReader, codepage: CodePage):
        type_id = reader.read_u32_le()
        self.min_version = 0
        if type_id == 0:
            self.type = "empty"
            self.value = None
        elif type_id == 1:
            self.type = "null"
            self.value = None
        elif type_id == 2:
            self.type = "i16"
            self.value = reader.read_i16_le()
        elif type_id == 3:
            self.type = "i32"
            self.value = reader.read_i32_le()
        elif type_id == 16:
            self.type = "i8"
            self.value = reader.read_i8()
            self.min_version = 1
        elif type_id == 30:
            self.type = "str"
            length = reader.read_u32_le()
            if length != 0:
                length -= 1
            self.value = codepage.decode(reader.read_bytes(length))
            if reader.read_u8() != 0:
                raise ValueError("String value should be null-terminated")
        elif type_id == 64:
            self.type = "ts"
            self.value = to_datetime(reader.read_u64_le())
        else:
            raise ValueError(f"Unsupported property type: {type_id}")
