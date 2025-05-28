PAGES = {
    0: "utf-8",
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
        return data.decode(self.encoding)


CodePage.DEFAULT = CodePage(0)
