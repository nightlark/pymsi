PAGES = {
    # CP 0 is the "system default", which is ambiguous and requires special handling
    0: None,
    932: "cp932",
    936: "gbk",
    949: "cp949",
    950: "cp950",
    951: "cp950",
    1250: "cp1250",
    1251: "cp1251",
    1252: "cp1252",
    1253: "cp1253",
    1254: "cp1254",
    1255: "cp1255",
    1256: "cp1256",
    1257: "cp1257",
    1258: "cp1258",
    10000: "mac_roman",
    10007: "mac_cyrillic",
    20127: "ascii",
    28591: "latin_1",
    28592: "iso8859_2",
    28593: "iso8859_3",
    28594: "iso8859_4",
    28595: "iso8859_5",
    28596: "iso8859_6",
    28597: "iso8859_7",
    28598: "iso8859_8",
    65000: "utf-7",
    65001: "utf-8",
}


class CodePage:
    DEFAULT: "CodePage"

    def __init__(self, id: int):
        if id not in PAGES:
            raise ValueError(f"Unsupported code page ID: {id}")
        self.id = id
        self.encoding = PAGES[id]

    def decode(self, data: bytes) -> str:
        # If a specific known encoding (non-neutral) was specified, use it
        if self.encoding:
            return data.decode(self.encoding)

        # Handle Code Page 0 (Neutral/System Default)
        if self.id == 0:
            # 1. Try utf-8 first, since modern MSIs may use it for neutral.
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                pass

            # 2. Try Windows-1252 (most common for older MSI files)
            # This will handle typical (c), (r), and western accented characters
            # The codec defines some byte values as undefined, so skip if it has those
            if all(b not in (0x81, 0x8D, 0x8F, 0x90, 0x9D) for b in data):
                try:
                    return data.decode("cp1252")
                except UnicodeDecodeError:
                    pass

            # 3. Last resort, latin-1 (iso-8859-1)
            # Every byte (0-255) is mapped to a character, but may look like gibberish
            return data.decode("latin_1")


CodePage.DEFAULT = CodePage(0)
