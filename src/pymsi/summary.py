import datetime
from typing import List, Optional

from .propset import PropertySet

FMTID = b"\xe0\x85\x9f\xf2\xf9\x4f\x68\x10\xab\x91\x08\x00\x2b\x27\xb3\xd9"

PROPERTY_TITLE = 2
PROPERTY_SUBJECT = 3
PROPERTY_AUTHOR = 4
PROPERTY_COMMENTS = 6
PROPERTY_TEMPLATE = 7
PROPERTY_UUID = 9
PROPERTY_CREATION_TIME = 12
PROPERTY_WORD_COUNT = 15
PROPERTY_CREATING_APP = 18


class Summary:
    def __init__(self, stream):
        self.properties = PropertySet(stream)
        if self.properties.fmtid != FMTID:
            raise ValueError("Invalid format identifier for Summary Info stream")

    def arch(self):
        value = self.properties.get(PROPERTY_TEMPLATE)
        if isinstance(value, str):
            return value.split(";")[0]
        return None

    def author(self):
        value = self.properties.get(PROPERTY_AUTHOR)
        if isinstance(value, str):
            return value
        return None

    def comments(self):
        value = self.properties.get(PROPERTY_COMMENTS)
        if isinstance(value, str):
            return value
        return None

    def creating_application(self):
        value = self.properties.get(PROPERTY_CREATING_APP)
        if isinstance(value, str):
            return value
        return None

    def creation_time(self):
        value = self.properties.get(PROPERTY_CREATION_TIME)
        if isinstance(value, datetime.datetime):
            return value
        return None

    def languages(self) -> Optional[List[int]]:
        value = self.properties.get(PROPERTY_TEMPLATE)
        if isinstance(value, str):
            template = value.split(";")
            if len(template) > 1:
                return [int(lang) for lang in template[1:]]
            return []
        return None

    def subject(self):
        value = self.properties.get(PROPERTY_SUBJECT)
        if isinstance(value, str):
            return value
        return None

    def title(self):
        value = self.properties.get(PROPERTY_TITLE)
        if isinstance(value, str):
            return value
        return None

    def uuid(self):
        value = self.properties.get(PROPERTY_UUID)
        if isinstance(value, str):
            return value
        return None

    def word_count(self):
        value = self.properties.get(PROPERTY_WORD_COUNT)
        if isinstance(value, int):
            return value
        return None

    def __str__(self):
        props = []
        if self.arch():
            props.append(("arch", self.arch()))
        if self.author():
            props.append(("author", self.author()))
        if self.comments():
            props.append(("comments", self.comments()))
        if self.creating_application():
            props.append(("creating_application", self.creating_application()))
        if self.creation_time():
            props.append(("creation_time", self.creation_time()))
        if self.languages():
            props.append(("languages", self.languages()))
        if self.subject():
            props.append(("subject", self.subject()))
        if self.title():
            props.append(("title", self.title()))
        if self.uuid():
            props.append(("uuid", self.uuid()))
        if self.word_count() is not None:
            props.append(("word_count", self.word_count()))
        return f"Summary({', '.join(f'{k}={repr(v)}' for k, v in props)})"
