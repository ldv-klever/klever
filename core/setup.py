#!/usr/bin/env python3
#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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
from setuptools import setup, find_packages

setup(name='KleverCore',
      use_scm_version={'root': os.path.pardir},
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
