from .codepage import CodePage
from .constants import *
from .reader import BinaryReader
from .timestamp import to_datetime


class PropertySet:
    def __init__(self, stream):
        reader = BinaryReader(stream)
        bom = reader.read_u16_le()
        assert bom == BOM

        file_version = reader.read_u16_le()
        assert file_version in [0, 1]

        self.os_version = reader.read_u16_le()
        self.os = reader.read_u16_le()
        assert self.os in [0, 1, 2]

        self.clsid = reader.read_bytes(16)

        assert reader.read_u32_le() >= 1

        # Section header
        self.fmtid = reader.read_bytes(16)
        section_offset = reader.read_u32_le()

        # Section
        reader.seek(section_offset)
        _section_size = reader.read_u32_le()
        num_props = reader.read_u32_le()
        prop_offsets = {}
        for _ in range(num_props):
            name = reader.read_u32_le()
            offset = reader.read_u32_le()
            assert name not in prop_offsets, f"Duplicate property name: {name}"
            prop_offsets[name] = offset

        if PROPERTY_CODEPAGE in prop_offsets:
            codepage_offset = prop_offsets[PROPERTY_CODEPAGE]
            reader.seek(section_offset + codepage_offset)
            value = PropertyValue(reader, CodePage.DEFAULT)
            self.codepage = CodePage(value.value)
        else:
            self.codepage = CodePage.DEFAULT

        self.properties = {}
        for name, offset in prop_offsets.items():
            reader.seek(section_offset + offset)
            value = PropertyValue(reader, self.codepage)
            assert value.min_version <= file_version, (
                f"Property {name} ({value.type}) version {value.min_version} is not supported by file version {file_version}"
            )
            self.properties[name] = value

    # Returns the raw value or None; quiet-fails
    def get(self, name):
        if not isinstance(name, int):
            raise TypeError("Name must be of type int")
        prop = self.properties.get(name)
        if prop is not None:
            return prop.value
        return None

    # Returns the property's raw value or throws
    def __getitem__(self, name):
        if not isinstance(name, int):
            raise TypeError("Name must be of type int")
        return self.properties[name].value

    def __contains__(self, name):
        if not isinstance(name, int):
            raise TypeError("Name must be of type int")
        return name in self.properties


class PropertyValue:
    def __init__(self, reader, codepage):
        type_id = reader.read_u32_le()
        self.min_version = 0
        match type_id:
            case 0:
                self.type = "empty"
                self.value = None
            case 1:
                self.type = "null"
                self.value = None
            case 2:
                self.type = "i16"
                self.value = reader.read_i16_le()
            case 3:
                self.type = "i32"
                self.value = reader.read_i32_le()
            case 16:
                self.type = "i8"
                self.value = reader.read_i8()
                self.min_version = 1
            case 30:
                self.type = "str"
                length = reader.read_u32_le()
                if length != 0:
                    length -= 1
                self.value = codepage.decode(reader.read_bytes(length))
                assert reader.read_u8() == 0, "String value should be null-terminated"
            case 64:
                self.type = "ts"
                self.value = to_datetime(reader.read_u64_le())
            case _:
                raise ValueError(f"Unsupported property type: {type_id}")
