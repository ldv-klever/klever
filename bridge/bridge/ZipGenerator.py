#
# Copyright (c) 2019 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import struct
import time
import zlib

from zipfile import ZipInfo, ZIP_DEFLATED, ZIP64_LIMIT, ZIP_FILECOUNT_LIMIT


CHUNK_SIZE = 1024 * 64


class LargeZipFile(Exception):
    pass


# Here are some struct module formats for reading headers
structEndArchive = b"<4s4H2LH"
stringEndArchive = b"PK\005\006"
structCentralDir = "<4s4B4HL2L5H2L"
stringCentralDir = b"PK\001\002"
structFileHeader = "<4s2B4HL2L2H"
stringFileHeader = b"PK\003\004"
structEndArchive64Locator = "<4sLQL"
stringEndArchive64Locator = b"PK\x06\x07"
structEndArchive64 = "<4sQ2H2L4Q"
stringEndArchive64 = b"PK\x06\x06"
stringDataDescriptor = b"PK\x07\x08"  # magic number for data descriptor


class ZipStream:
    def __init__(self):
        self._filelist = []
        self._data_p = 0

    def __get_data(self, data):
        self._data_p += len(data)
        return data

    def compress_file(self, filename, arcname):
        st = os.stat(filename)
        zinfo = ZipInfo(arcname, time.localtime(time.time())[:6])
        zinfo.external_attr = (st[0] & 0xFFFF) << 16
        zinfo.compress_type = ZIP_DEFLATED
        zinfo.flag_bits = 0x08
        zinfo.header_offset = self._data_p

        cmpr = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
        with open(filename, "rb") as fp:
            zinfo.CRC = crc = 0
            zinfo.compress_size = 0
            zinfo.file_size = 0
            yield self.__get_data(zinfo.FileHeader())

            while 1:
                buf = fp.read(CHUNK_SIZE)
                if not buf:
                    break
                zinfo.file_size += len(buf)
                crc = zlib.crc32(buf, crc) & 0xffffffff
                if cmpr:
                    buf = cmpr.compress(buf)
                    zinfo.compress_size += len(buf)
                yield self.__get_data(buf)
        if cmpr:
            buf = cmpr.flush()
            zinfo.compress_size += len(buf)
            yield self.__get_data(buf)
        else:
            zinfo.compress_size = zinfo.file_size
        zinfo.CRC = crc

        zip64 = zinfo.file_size > ZIP64_LIMIT or zinfo.compress_size > ZIP64_LIMIT
        fmt = '<4sLQQ' if zip64 else '<4sLLL'
        data_descriptor = struct.pack(fmt, stringDataDescriptor, zinfo.CRC, zinfo.compress_size, zinfo.file_size)
        yield self.__get_data(data_descriptor)
        self._filelist.append(zinfo)

    def compress_buffer(self, arcname, buffer):
        zinfo = ZipInfo(filename=arcname, date_time=time.localtime(time.time())[:6])
        zinfo.compress_type = ZIP_DEFLATED
        zinfo.compress_size = 0
        zinfo.flag_bits = 0x08
        zinfo.external_attr = 0o600 << 16
        zinfo.file_size = 0
        zinfo.header_offset = self._data_p
        zinfo.CRC = crc = 0
        cmpr = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)

        yield self.__get_data(zinfo.FileHeader())

        buffer.seek(0)
        while 1:
            buf = buffer.read(CHUNK_SIZE)
            if not buf:
                break
            zinfo.file_size += len(buf)
            crc = zlib.crc32(buf, crc) & 0xffffffff
            if cmpr:
                buf = cmpr.compress(buf)
                zinfo.compress_size += len(buf)
            yield self.__get_data(buf)

        if cmpr:
            buf = cmpr.flush()
            zinfo.compress_size += len(buf)
            yield self.__get_data(buf)
        else:
            zinfo.compress_size = zinfo.file_size

        zinfo.CRC = crc
        zip64 = zinfo.file_size > ZIP64_LIMIT or zinfo.compress_size > ZIP64_LIMIT

        fmt = '<4sLQQ' if zip64 else '<4sLLL'
        data_descriptor = struct.pack(fmt, stringDataDescriptor, zinfo.CRC, zinfo.compress_size, zinfo.file_size)
        yield self.__get_data(data_descriptor)

        self._filelist.append(zinfo)

    def compress_string(self, arcname, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        zinfo = ZipInfo(filename=arcname, date_time=time.localtime(time.time())[:6])
        zinfo.compress_type = ZIP_DEFLATED
        zinfo.external_attr = 0o600 << 16
        zinfo.file_size = len(data)
        zinfo.header_offset = self._data_p
        zinfo.CRC = zlib.crc32(data) & 0xffffffff
        cmpr = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
        if cmpr:
            data = cmpr.compress(data) + cmpr.flush()
            zinfo.compress_size = len(data)
        else:
            zinfo.compress_size = zinfo.file_size
        zip64 = zinfo.file_size > ZIP64_LIMIT or zinfo.compress_size > ZIP64_LIMIT

        yield self.__get_data(zinfo.FileHeader(zip64))
        yield self.__get_data(data)
        self._filelist.append(zinfo)

    def compress_stream(self, arcname, datagen):
        zinfo = ZipInfo(arcname, time.localtime(time.time())[:6])
        zinfo.external_attr = 0o600 << 16
        zinfo.compress_type = ZIP_DEFLATED
        zinfo.flag_bits = 0x08
        zinfo.header_offset = self._data_p

        cmpr = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
        zinfo.CRC = crc = 0
        zinfo.compress_size = 0
        zinfo.file_size = 0

        yield self.__get_data(zinfo.FileHeader())

        for buf in datagen:
            if not buf:
                continue
            zinfo.file_size += len(buf)
            crc = zlib.crc32(buf, crc) & 0xffffffff
            if cmpr:
                buf = cmpr.compress(buf)
                zinfo.compress_size += len(buf)
            yield self.__get_data(buf)

        if cmpr:
            buf = cmpr.flush()
            zinfo.compress_size += len(buf)
            yield self.__get_data(buf)
        else:
            zinfo.compress_size = zinfo.file_size
        zinfo.CRC = crc

        zip64 = zinfo.file_size > ZIP64_LIMIT
        fmt = '<4sLQQ' if zip64 else '<4sLLL'
        data_descriptor = struct.pack(fmt, stringDataDescriptor, zinfo.CRC, zinfo.compress_size, zinfo.file_size)
        yield self.__get_data(data_descriptor)
        self._filelist.append(zinfo)

    def close_stream(self):
        data = []
        pos1 = self._data_p
        for zinfo in self._filelist:
            dt = zinfo.date_time
            dosdate = (dt[0] - 1980) << 9 | dt[1] << 5 | dt[2]
            dostime = dt[3] << 11 | dt[4] << 5 | (dt[5] // 2)
            extra = []
            if zinfo.file_size > ZIP64_LIMIT or zinfo.compress_size > ZIP64_LIMIT:
                extra.append(zinfo.file_size)
                extra.append(zinfo.compress_size)
                file_size = 0xffffffff
                compress_size = 0xffffffff
            else:
                file_size = zinfo.file_size
                compress_size = zinfo.compress_size

            if zinfo.header_offset > ZIP64_LIMIT:
                extra.append(zinfo.header_offset)
                header_offset = 0xffffffff
            else:
                header_offset = zinfo.header_offset

            extra_data = zinfo.extra
            min_version = 0
            if extra:
                extra_data = struct.pack('<HH' + 'Q'*len(extra), 1, 8*len(extra), *extra) + extra_data
                min_version = 45

            extract_version = max(min_version, zinfo.extract_version)
            create_version = max(min_version, zinfo.create_version)
            filename, flag_bits = zinfo._encodeFilenameFlags()

            centdir = struct.pack(
                structCentralDir, stringCentralDir,
                create_version, zinfo.create_system, extract_version,
                zinfo.reserved, flag_bits, zinfo.compress_type,
                dostime, dosdate, zinfo.CRC, compress_size, file_size,
                len(filename), len(extra_data), len(zinfo.comment),
                0, zinfo.internal_attr, zinfo.external_attr, header_offset
            )
            data.append(self.__get_data(centdir))
            data.append(self.__get_data(filename))
            data.append(self.__get_data(extra_data))
            data.append(self.__get_data(zinfo.comment))

        pos2 = self._data_p
        count = len(self._filelist)
        dir_size = pos2 - pos1
        dir_offset = pos1
        if count > ZIP_FILECOUNT_LIMIT or dir_offset > ZIP64_LIMIT or dir_size > ZIP64_LIMIT:
            zip64endrec = struct.pack(
                structEndArchive64, stringEndArchive64, 44, 45, 45, 0, 0, count, count, dir_size, dir_offset
            )
            data.append(self.__get_data(zip64endrec))
            zip64locrec = struct.pack(structEndArchive64Locator, stringEndArchive64Locator, 0, pos2, 1)
            data.append(self.__get_data(zip64locrec))
            count = min(count, 0xFFFF)
            dir_size = min(dir_size, 0xFFFFFFFF)
            dir_offset = min(dir_offset, 0xFFFFFFFF)

        endrec = struct.pack(structEndArchive, stringEndArchive, 0, 0, count, count, dir_size, dir_offset, 0)
        data.append(self.__get_data(endrec))
        return b''.join(data)
