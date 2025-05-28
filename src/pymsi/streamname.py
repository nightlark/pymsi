from typing import Tuple

from .constants import TABLE_PREFIX, TABLE_PREFIX_UTF8


# variant of base64 encoding
def utf2mime(x):
    if x in range(ord("0"), ord("9") + 1):
        return x - ord("0")
    if x in range(ord("A"), ord("Z") + 1):
        return x - ord("A") + 10
    if x in range(ord("a"), ord("z") + 1):
        return x - ord("a") + 10 + 26
    if x == ord("."):
        return 10 + 26 + 26
    if x == ord("_"):
        return 10 + 26 + 26 + 1
    return None


# variant of base64 decoding
def mime2utf(x):
    if x < 10:
        return chr(x + ord("0"))
    if x < (10 + 26):
        return chr(x - 10 + ord("A"))
    if x < (10 + 26 + 26):
        return chr(x - 10 - 26 + ord("a"))
    if x == (10 + 26 + 26):
        return "."
    return "_"


def is_valid(name, isTable=False):
    if not name or (not isTable and name.startswith(TABLE_PREFIX)):
        return False
    else:
        # NOTE: this may not be 100% accurate; need to check if it is a byte count using a particular encoding
        return len(encode_unicode(name, isTable)) <= 31


def decode_unicode(name: str) -> Tuple[str, bool]:
    if len(name) < 1:
        return str(), False
    out = str()
    isTable = False
    name_enum = enumerate(name)
    if ord(name[0]) == ord(TABLE_PREFIX):
        isTable = True
        next(name_enum)
    for _idx, c in name_enum:
        value = ord(c)
        if value in range(0x3800, 0x4800):
            value = value - 0x3800
            out += mime2utf(value & 0x3F)
            out += mime2utf(value >> 6)
        elif value in range(0x4800, 0x4840):
            out += mime2utf(value - 0x4800)
        else:
            out += c
    return out, isTable


# encode using unicode
def encode_unicode(name: str, isTable: bool = False) -> str:
    out = str()
    if isTable:
        out += TABLE_PREFIX
    name_enum = enumerate(name)
    for idx, c1 in name_enum:
        value1 = utf2mime(ord(c1))
        if value1 is not None:
            if idx + 1 < len(name):
                value2 = utf2mime(ord(name[idx + 1]))
                if value2 is not None:
                    encoded = 0x3800 + (value2 << 6) + value1
                    out += chr(encoded)
                    next(name_enum)
                    continue
            encoded = 0x4800 + value1
            out += chr(encoded)
        else:
            out += c1
    return out


# this operates on utf-8 encoded bytes
def decode_utf8(name):
    out = str()
    isTable = False
    name_enum = enumerate(name)
    if name.startswith(TABLE_PREFIX_UTF8):
        isTable = True
        next(name_enum)
        next(name_enum)
        next(name_enum)
    for idx, c in name_enum:
        if idx + 2 >= len(name):
            break
        if (name[idx] == 0xE3 and name[idx + 1] >= 0xA0) or (
            name[idx] == 0xE4 and name[idx + 1] < 0xA0
        ):
            out += mime2utf(name[idx + 2] & 0x7F)
            out += mime2utf(name[idx + 1] ^ 0xA0)
            next(name_enum)
            next(name_enum)
            continue
        if name[idx] == 0xE4 and name[idx + 1] == 0xA0:
            out += mime2utf(name[idx + 2] & 0x7F)
            next(name_enum)
            next(name_enum)
            continue
        out += chr(c)
        if c >= 0xC1:
            idx2, c2 = next(name_enum)
            out += chr(c2)
        if c >= 0xE0:
            idx2, c2 = next(name_enum)
            out += chr(c2)
        if c >= 0xF0:
            idx2, c2 = next(name_enum)
            out += chr(c2)
    return out, isTable


# NOTE: very likely that this function isn't quite working yet
# works using the utf-8 character encoding
def encode_utf8(name, table=False):
    out = bytes()
    if table:
        out += chr(0xE4)
        out += chr(0xA1)
        out += chr(0x80)
    name_enum = enumerate(name)
    for idx, c in name_enum:
        if ord(c) < 0x80 and utf2mime(ord(c)) >= 0:
            ch = utf2mime(ord(c))
            next_ch = -1
            if idx + 1 < len(name):
                if ord(name[idx + 1]) < 0x80:
                    next_ch = utf2mime(ord(name[idx + 1]))
            if next_ch == -1:
                out += chr(0xE4)
                out += chr(0xA0)
                out += chr(0x80 | ch)
            else:
                out += chr(0xE3 + (next_ch >> 5))
                out += chr(0xA0 ^ next_ch)
                out += chr(0x80 | ch)
                next(name_enum)
        else:
            out += chr(c)
    return out
