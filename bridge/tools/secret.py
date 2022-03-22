import json
import os
import tempfile
import zipfile

from django.utils.translation import gettext_lazy as _

from bridge.vars import COVERAGE_FILE
from bridge.utils import BridgeException, ArchiveFileContent
from reports.models import CoverageArchive


class FixOldCoverage:
    def __init__(self):
        self._qs = CoverageArchive.objects.exclude(identifier='')
        self.count = 0

    @property
    def archives(self):
        return list(obj.archive.name for obj in self._qs)

    def fix_all(self):
        for cov_obj in self._qs:
            try:
                res = ArchiveFileContent(cov_obj, 'archive', COVERAGE_FILE)
            except Exception as e:
                raise BridgeException(_("Error while extracting source file: %(error)s") % {'error': str(e)})
            data = json.loads(res.content.decode('utf8'))
            if 'coverage statistics' not in data:
                raise BridgeException(_('Common code coverage file does not contain statistics'))
            if self.__update_statistics(data['coverage statistics']):
                self.__update_archive(data, cov_obj.archive.path)

    def __update_statistics(self, statistics):
        changed = False
        for fname in statistics:
            if len(statistics[fname]) == 4 and statistics[fname][0] == statistics[fname][2] == 0:
                statistics[fname] = [statistics[fname][1], statistics[fname][3]]
                changed = True
        return changed

    def __update_archive(self, data, archive_path):
        self.count += 1
        tmpfd, tmpname = tempfile.mkstemp(dir=os.path.dirname(archive_path))
        os.close(tmpfd)

        with zipfile.ZipFile(archive_path, 'r') as zin:
            with zipfile.ZipFile(tmpname, 'w') as zout:
                zout.comment = zin.comment  # preserve the comment
                for item in zin.infolist():
                    if item.filename != COVERAGE_FILE:
                        zout.writestr(item, zin.read(item.filename))

        cached_archive = os.path.splitext(archive_path)[0] + '_old.zip'
        os.rename(archive_path, cached_archive)
        try:
            os.rename(tmpname, archive_path)
            with zipfile.ZipFile(archive_path, mode='a', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(COVERAGE_FILE, json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as e:
            try:
                os.remove(archive_path)
            finally:
                os.rename(cached_archive, archive_path)
            raise BridgeException(e)
        else:
            os.remove(cached_archive)
