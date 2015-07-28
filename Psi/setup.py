try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

config = {
    'description': 'TODO',
    'author': 'Evgeny Novikov',
    'url': 'TODO: URL to get it at.',
    'download_url': 'TODO: Where to download it.',
    'author_email': 'novikov@ispras.ru',
    'version': '0.1',
    'install_requires': ['nose'],
    'packages': ['Psi'],
    'scripts': [],
    'name': 'Psi'
}

setup(**config)
