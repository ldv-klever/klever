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

import copy
import pytest

from klever.core.vtg.emg.common.process.actions import *


@pytest.fixture
def action1():
    return BehAction('test1')


@pytest.fixture
def action2():
    return BehAction('test11')


@pytest.fixture
def operator():
    return Operator()


def test_savepoint():
    name = "test1"
    v1 = 'x1'
    v2 = 'x2'
    statements = [v1, v2]
    pnt = Savepoint(name, statements)

    # Test __str__
    assert str(pnt) == name

    # Test atatements
    for i1, i2 in zip(pnt.statements, statements):
        assert i1 == i2

    statements.pop()
    assert len(statements) != pnt.statements

    # Test hashing
    new = {pnt}
    assert pnt in new


def test_my_operator(action1, action2, operator):
    operator.append(action1)
    assert action1 in operator
    assert action1.my_operator
    assert operator[0]
    operator[0] = action2
    assert action1.my_operator is not operator
    assert action2.my_operator is operator
    assert len(operator) == 1


def test_operator(operator, action1, action2):
    # Test str
    assert str(operator)

    # Test set/get item
    operator.append(action2)
    operator[0] = action1
    assert action1.my_operator is operator
    assert action2.my_operator is None
    assert operator[0] is action1
    assert len(operator) == 1

    # Test deletion
    del operator[0]
    assert len(operator) == 0
    assert not action1.my_operator

    # Test insert
    operator.append(action2)
    operator.insert(0, action1)
    assert action1.my_operator is operator
    assert action2.my_operator is operator
    assert operator[0] is action1
    assert operator[1] is action2
    assert len(operator) == 2

    # Test remove
    operator.remove(action2)
    assert len(operator) == 1
    assert operator[0] is action1
    assert not action2.my_operator

    # Test replace
    operator.replace(action1, action2)
    assert len(operator) == 1
    assert operator[0] is action2
    assert not action1.my_operator
    assert action2.my_operator is operator

    # Test index
    operator.append(action1)
    assert operator.index(action1) == 1
    assert operator.index(action2) == 0
    assert action1.my_operator is operator
    assert action2.my_operator is operator
    assert operator[0] is action2
    assert operator[1] is action1


def test_actions():
    # todo: Implement
    raise NotImplementedError
    # assert {action1}
    # assert action1 == copy.deepcopy(action1)
    # assert action1 < action2
    #
    # operator.append(action1)
    # assert action1.my_operator is operator
    # clone = copy.deepcopy(action1)
    # assert clone.condition is not action1.condition
    # assert clone.savepoints is not action1.savepoints
    # assert clone.my_operator is None
    # assert action1.my_operator is operator
