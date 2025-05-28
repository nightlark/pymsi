import struct

from olefile.olefile import OleStream


class BinaryReader:
    def __init__(self, stream: OleStream):
        self.stream = stream

    def read_u8(self) -> int:
        return struct.unpack("<B", self.stream.read(1))[0]

    def read_i8(self) -> int:
        return struct.unpack("<b", self.stream.read(1))[0]

    def read_u16_le(self) -> int:
        return struct.unpack("<H", self.stream.read(2))[0]

    def read_i16_le(self) -> int:
        return struct.unpack("<h", self.stream.read(2))[0]

    def read_u32_le(self) -> int:
        return struct.unpack("<I", self.stream.read(4))[0]

    def read_i32_le(self) -> int:
        return struct.unpack("<i", self.stream.read(4))[0]

    def read_u64_le(self) -> int:
        return struct.unpack("<Q", self.stream.read(8))[0]

    def read_i64_le(self) -> int:
        return struct.unpack("<q", self.stream.read(8))[0]

    def read_f32_le(self) -> float:
        return struct.unpack("<f", self.stream.read(4))[0]

    def read_f64_le(self) -> float:
        return struct.unpack("<d", self.stream.read(8))[0]

    def read_bytes(self, size) -> bytes:
        return self.stream.read(size)

    def seek(self, offset):
        self.stream.seek(offset)

    def size(self) -> int:
        return self.stream.size

    def tell(self) -> int:
        return self.stream.tell()

    def iseof(self) -> bool:
        return self.tell() >= self.size()
