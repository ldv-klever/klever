import os
import tarfile


class Job:
    format = 1
    archive = 'job.tar.gz'
    dir = 'job'
    class_file = os.path.join(dir, 'class')

    def __init__(self, logger, id):
        self.logger = logger
        self.logger.debug('Support jobs of format "{0}"'.format(self.format))
        self.id = id
        self.logger.debug('Job identifier is "{0}"'.format(id))
        self.type = None
        self.conf = None
        self.sub_jobs = []

    def get_class(self):
        self.logger.info('Get job class')
        with open(self.class_file, encoding='ascii') as fp:
            self.type = fp.read()
        self.logger.debug('Job class is "{0}"'.format(self.type))

    def extract_archive(self):
        self.logger.info('Extract job archive "{0}" to directory "{1}"'.format(self.archive, self.dir))
        with tarfile.open(self.archive) as TarFile:
            TarFile.extractall(self.dir)
