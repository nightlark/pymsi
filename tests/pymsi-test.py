import olefile
import pymsi

ole = olefile.OleFileIO("test.msi")

# Decode all the stream names in the OLE file
for k in ole.root.kids:
    print(pymsi.decode_streamname_unicode(k.name))

##########################################################################

# Read all the strings from the _StringData and _StringPool tables
fstrdata = ole.openstream(pymsi.encode_streamname_unicode("_StringData", True))
fstrpool = ole.openstream(pymsi.encode_streamname_unicode("_StringPool", True))

strdata = fstrdata.read()
print(len(strdata))
print(str(strdata[:10]))

codepage_id = int.from_bytes(fstrpool.read(2), byteorder="little")
long_strref = int.from_bytes(fstrpool.read(2), byteorder="little")
print(f"codepage:{codepage_id} longrefs:{long_strref}")

stroffset = 0
nextbytes = fstrpool.read(4)
while len(nextbytes) == 4:
    strlen = int.from_bytes(nextbytes[:2], byteorder="little")
    strrefcnt = int.from_bytes(nextbytes[2:4], byteorder="little")

    # check if big string
    if strlen == 0 and strrefcnt != 0:
        print("Empty str or big str?")
        nextbytes = fstrpool.read(4)
        # calculate long strlen before cloberring refcnt
        strlen = strrefcnt << 16
        strlen += int.from_bytes(nextbytes[:2], byteorder="little")
        strrefcnt = int.from_bytes(nextbytes[2:4], byteorder="little")

    print(str(strdata[stroffset : stroffset + strlen]))
    print(f"len:{strlen} refcnt:{strrefcnt}")

    stroffset += strlen
    nextbytes = fstrpool.read(4)

##########################################################################

# Read everything from the _Tables and _Columns tables
# these have information needed to read tables with details on install files/directories
