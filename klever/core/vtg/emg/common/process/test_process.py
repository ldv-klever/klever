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

from klever.core.vtg.emg.common.process import Process
from klever.core.vtg.emg.common.process.parser import parse_process
from klever.core.vtg.emg.common.process.actions import Receive, Dispatch, Block, Concatenation, Choice


@pytest.fixture
def process():
    process = Process('test')
    test = "(((a).<b> | [c]) . [d]) | [e]"

    # Parse
    assert parse_process(process, test)
    process.actions['a'] = Receive('a')
    process.actions['b'] = Block('b')
    for name in 'cde':
        process.actions[name] = Dispatch(name)

    return process


@pytest.fixture
def new():
    return Block('r')


def test_add_condition(process):
    new = process.actions.add_condition('x', ['0 == 0'], ['x = 1;'], 'This is a test')
    assert new and isinstance(new, Block)
    assert str(new) in process.actions
    assert not process.actions.behaviour(new.name)


def test_add_replace_action(new, process):
    new = Block('r')
    old = process.actions['d']
    operator = process.actions.behaviour('d').pop().my_operator

    assert isinstance(operator, Concatenation)
    process.actions.replace_action(old, new, purge=True)

    assert operator[-1].kind is Block
    assert operator[-1].name == 'r'
    assert operator[-1].description is new
    assert str(old) not in process.actions
    assert not process.actions.behaviour(str(old))
    assert len(process.actions.behaviour(str(new))) == 1


def test_add_insert_action(new, process):
    target = process.actions['d']
    operator = process.actions.behaviour('d').pop().my_operator

    process.actions.insert_action(new, target, before=True)
    assert operator[-2].kind is Block, repr(operator)
    assert operator[-2].name == 'r', repr(operator)
    assert operator[-2].description is new, f"{repr(operator)} {operator[-1].description}"
    assert str(new) in process.actions
    assert operator[-1].kind is Dispatch, repr(operator)
    assert operator[-1].name == 'd', repr(operator)
    assert operator[-1].description is target, f"{repr(operator)} {operator[-1].description}"
    assert str(target) in process.actions

    process.actions.insert_action(new, target, before=False)
    assert operator[-1].kind is Block, repr(operator)
    assert operator[-1].name == 'r', repr(operator)
    assert operator[-1].description is new, repr(operator)
    assert str(new) in process.actions
    assert operator[-2].kind is Dispatch, repr(operator)
    assert operator[-2].name == 'd', repr(operator)
    assert operator[-2].description is target, repr(operator)
    assert str(target) in process.actions


def test_insert_before(new, process):
    target = process.actions['c']
    operator = process.actions.behaviour('c').pop().my_operator
    assert isinstance(operator, Concatenation)
    assert isinstance(operator.my_operator, Choice)

    # Simple case
    process.actions.insert_action(new, target, before=True)
    assert isinstance(operator, Concatenation)
    assert isinstance(operator.my_operator, Choice)
    assert str(operator[0].description) == 'r'
    assert str(operator[1].description) == 'c'


def test_insert_choice(process):
    target = process.actions['c']
    operator = process.actions.behaviour('c').pop().my_operator
    assert isinstance(operator, Concatenation)
    operator = operator.my_operator
    assert isinstance(operator, Choice)
    assert len(operator) == 2

    # Add more options
    new_x1 = process.actions.add_condition('x1', [], [], 'This is a test')
    new_x2 = process.actions.add_condition('x2', [], [], 'This is a test')
    process.actions.insert_alternative_action(new_x1, target)
    process.actions.insert_alternative_action(new_x2, target)
    assert len(operator) == 4

    # Then add precondition to x1
    new_x3 = process.actions.add_condition('x3', [], [], 'This is a test')
    process.actions.insert_action(new_x3, new_x1, before=True)
    operator = process.actions.behaviour('x1').pop().my_operator
    assert isinstance(operator, Concatenation)
    assert str(operator[0].description) == 'x3'
    assert str(operator[1].description) == 'x1'
