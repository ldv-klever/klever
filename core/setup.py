import os
from setuptools import setup, find_packages

setup(name='KleverCore',
      use_scm_version={'root': os.path.pardir, 'local_scheme': 'dirty-tag'},
      description='TODO: a single line describing the package',
      author='Evgeny Novikov',
      author_email='novikov@ispras.ru',
      url='http://forge.ispras.ru/projects/klever',
      download_url='TODO: a URL to download the package',
      packages=find_packages(),
      package_data={'core.lkbce': ['wrappers/gcc', 'wrappers/ld', 'wrappers/mv']},
      scripts=['bin/klever-core'],
      setup_requires=['setuptools_scm'],
      requires=['jinja2', 'graphviz', 'ply', 'requests'],
      classifiers=['TODO: a list of categories for the package'],
      )
