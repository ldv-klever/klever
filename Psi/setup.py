try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(name='Psi',
      version='0.1',
      description='TODO: a single line describing the package',
      author='Evgeny Novikov',
      author_email='novikov@ispras.ru',
      url='http://forge.ispras.ru/projects/klever',
      download_url='TODO: a URL to download the package',
      packages=['psi', 'psi.lkbce', 'psi.lkvog', 'psi.avtg', 'psi.vtg'],
      scripts=['bin/psi'],
      requires=['jinja2'],
      classifiers=['TODO: a list of categories for the package'],
      )
