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
from klever.core.vtg.emg.common.process.labels import Label
from klever.core.vtg.emg.common.process.parser import parse_process
from klever.core.vtg.emg.common.process.actions import Receive, Dispatch, Block


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

    for name in ('l1', 'l2'):
        process.labels[name] = Label(name)

    return process


@pytest.fixture
def clone(process):
    return process.clone()


def test_labels(process, clone):
    for label_name in process.labels:
        assert label_name in clone.labels, f'Missing label {label_name}'

    assert process.labels['l1'] is not clone.labels['l2']
    process.labels['l3'] = Label('l3')
    assert 'l3' not in clone.labels


def test_clone_action(process, clone):
    assert process.actions['d'] is not clone.actions['d']
    assert process.actions.behaviour('d').pop().description is process.actions['d']
    assert clone.actions.behaviour('d').pop().description is clone.actions['d']


def test_clone_actions(process, clone):
    assert process.actions is not clone.actions
    for i in process.actions.behaviour():
        assert i not in clone.actions.behaviour()


def test_clone_behaviours(process, clone):
    operator = process.actions.behaviour('d').pop().my_operator
    del process.actions['d']

    assert clone.actions['d']
    assert clone.actions.behaviour('d').pop()
    assert len(clone.actions.behaviour('d').pop().my_operator) == len(operator) + 1
