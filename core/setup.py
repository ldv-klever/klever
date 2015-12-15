try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(name='Klever Core',
      version='0.1',
      description='TODO: a single line describing the package',
      author='Evgeny Novikov',
      author_email='novikov@ispras.ru',
      url='http://forge.ispras.ru/projects/klever',
      download_url='TODO: a URL to download the package',
      packages=['core', 'core.lkbce', 'core.lkvog', 'core.avtg', 'core.vtg'],
      scripts=['bin/klever-core'],
      requires=['jinja2', 'requests'],
      classifiers=['TODO: a list of categories for the package'],
      )
