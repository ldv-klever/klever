#
# Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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

import pytest
from klever.core.vtg.emg.common.process.actions import Behaviour, Dispatch, Subprocess
from klever.core.vtg.emg.decomposition.scenario import Path


@pytest.fixture()
def path1():
    a = Behaviour('a', Dispatch)
    b = Behaviour('b', Dispatch)
    c = Behaviour('c', Subprocess)
    new = Path()
    new.data = [a, b, c]
    return new


@pytest.fixture()
def path2():
    a = Behaviour('a', Dispatch)
    b = Behaviour('b', Dispatch)
    c = Behaviour('f', Dispatch)
    new = Path()
    new.data = [a, b, c]
    return new


@pytest.fixture()
def path3():
    a = Behaviour('a', Dispatch)
    b = Behaviour('b', Dispatch)
    c = Behaviour('c', Subprocess)
    new = Path()
    new.data = [a, b, c]
    return new


def test_copy(path1):
    path1.name = 'test'
    x = Path(path1)
    assert x.name == path1.name
    assert isinstance(x.data, list)
    assert x.data is not path1.data
    assert x == path1


def test_eq(path1, path2, path3):
    assert path1 != path2
    assert path1 == path3
    path1.pop()
    path2.pop()
    assert path1 == path2


def test_inclusive_path(path1, path2):
    assert path1.included(path2)


def test_add(path1, path2):
    path = path2 + path1
    assert path
    assert len(path) == len(path2) + len(path1)
    assert path[-1].name == path1[-1].name


def test_iadd(path1, path2):
    path2 += path1
    for i in range(len(path1)):
        assert path2[-(i+1)].name == list(reversed(path1))[i].name


def test_name(path1, path2):
    path1.name = 'path1'
    path2.name = 'path2'
    path = path1 + path2
    assert path.name == 'path1_path2'


def test_hash(path1, path2, path3):
    collection = set()
    collection.add(path1)
    assert path1 in collection
    collection.add(path2)
    assert len(collection) == 2
    collection.add(path3)
    assert len(collection) == 2
