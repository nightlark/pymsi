import uuid

CATEGORY_TEXT = "Text"
CATEGORY_UPPERCASE = "UpperCase"
CATEGORY_LOWERCASE = "LowerCase"
CATEGORY_INTEGER = "Integer"
CATEGORY_DOUBLEINTEGER = "DoubleInteger"
CATEGORY_TIMEDATE = "TimeDate"
CATEGORY_IDENTIFIER = "Identifier"
CATEGORY_PROPERTY = "Property"
CATEGORY_FILENAME = "Filename"
CATEGORY_WILDCARDFILENAME = "WildCardFilename"
CATEGORY_PATH = "Path"
CATEGORY_PATHS = "Paths"
CATEGORY_ANYPATH = "AnyPath"
CATEGORY_DEFAULTDIR = "DefaultDir"
CATEGORY_REGPATH = "RegPath"
CATEGORY_FORMATTED = "Formatted"
CATEGORY_FORMATTEDSDDLTEXT = "FormattedSDDLText"
CATEGORY_TEMPLATE = "Template"
CATEGORY_CONDITION = "Condition"
CATEGORY_GUID = "GUID"
CATEGORY_VERSION = "Version"
CATEGORY_LANGUAGE = "Language"
CATEGORY_BINARY = "Binary"
CATEGORY_CUSTOMSOURCE = "CustomSource"
CATEGORY_CABINET = "Cabinet"
CATEGORY_SHORTCUT = "Shortcut"
CATEGORIES_ALL = [
    CATEGORY_TEXT,
    CATEGORY_UPPERCASE,
    CATEGORY_LOWERCASE,
    CATEGORY_INTEGER,
    CATEGORY_DOUBLEINTEGER,
    CATEGORY_TIMEDATE,
    CATEGORY_IDENTIFIER,
    CATEGORY_PROPERTY,
    CATEGORY_FILENAME,
    CATEGORY_WILDCARDFILENAME,
    CATEGORY_PATH,
    CATEGORY_PATHS,
    CATEGORY_ANYPATH,
    CATEGORY_DEFAULTDIR,
    CATEGORY_REGPATH,
    CATEGORY_FORMATTED,
    CATEGORY_FORMATTEDSDDLTEXT,
    CATEGORY_TEMPLATE,
    CATEGORY_CONDITION,
    CATEGORY_GUID,
    CATEGORY_VERSION,
    CATEGORY_LANGUAGE,
    CATEGORY_BINARY,
    CATEGORY_CUSTOMSOURCE,
    CATEGORY_CABINET,
    CATEGORY_SHORTCUT,
]


def validate(category, data: str):
    if category == CATEGORY_TEXT:
        return True
    if category == CATEGORY_UPPERCASE:
        return data.isupper()
    if category == CATEGORY_LOWERCASE:
        return data.islower()
    if category == CATEGORY_INTEGER:
        try:
            return -32768 <= int(data) < 32767
        except ValueError:
            return False
    if category == CATEGORY_DOUBLEINTEGER:
        try:
            return -2147483648 <= int(data) < 2147483647
        except ValueError:
            return False
    if category == CATEGORY_IDENTIFIER:
        starts_valid = data and (data[0].isalpha() or data[0] == "_")
        all_valid = all(c.isalnum() or c == "_" or c == "." for c in data)
        return starts_valid and all_valid
    if category == CATEGORY_PROPERTY:
        substr = data[1:] if data.startswith("%") else data
        return validate(CATEGORY_IDENTIFIER, substr)
    if category == CATEGORY_GUID:
        if len(data) != 38:
            return False
        if not data.startswith("{") or not data.endswith("}"):
            return False
        if any(c.islower() for c in data):
            return False
        try:
            uuid.UUID(data[1:37])
            return True
        except ValueError:
            return False
    if category == CATEGORY_VERSION:
        parts = data.split(".")
        if len(parts) > 4:
            return False
        try:
            return all(0 <= int(part) < 65536 for part in parts)
        except ValueError:
            return False
    if category == CATEGORY_LANGUAGE:
        parts = data.split(".")
        return all(0 <= int(part) < 65536 for part in parts)
    if category == CATEGORY_CABINET:
        if data.startswith("#"):
            substr = data[1:]
            return validate(CATEGORY_IDENTIFIER, substr)
        else:
            parts = data.rsplit(".", 1)[::-1]
            if not parts:
                return False
            if not parts[0]:
                return False
            if len(parts[0]) > 8:
                return False
            if len(parts) >= 2 and len(parts[1]) > 3:
                return False
            return True
    return True  # Default for unimplemented categories
