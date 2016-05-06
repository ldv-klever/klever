from setuptools import setup, find_packages
from subprocess import getoutput

setup(name='KleverCore',
      version=getoutput('git --git-dir ../.git describe --always --abbrev=7 --dirty'),
      description='TODO: a single line describing the package',
      author='Evgeny Novikov',
      author_email='novikov@ispras.ru',
      url='http://forge.ispras.ru/projects/klever',
      download_url='TODO: a URL to download the package',
      packages=find_packages(),
      scripts=['bin/klever-core'],
      requires=['jinja2', 'graphviz', 'ply', 'requests'],
      classifiers=['TODO: a list of categories for the package'],
      )
