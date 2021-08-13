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
from klever.core.vtg.emg.common.process.actions import Dispatch


@pytest.fixture
def new():
    return Dispatch('d')


@pytest.fixture
def process():
    return Process('test')


def _prepare_empty_process(process):
    test = "(((a).<b> | [c]) . [d]) | [e]"
    assert parse_process(process, test)


def test_before_assignment(new, process):
    process.actions[str(new)] = new
    _prepare_empty_process(process)
    bvs = process.actions.behaviour(str(new))

    assert len(bvs) == 1
    assert bvs.pop().description is new


def test_after_assignment(new, process):
    _prepare_empty_process(process)
    process.actions[str(new)] = new
    bvs = process.actions.behaviour(str(new))

    assert len(bvs) == 1
    assert bvs.pop().description is new


def test_replacement(new, process):
    process.actions[str(new)] = new
    _prepare_empty_process(process)
    newest = Dispatch('d')
    process.actions[str(new)] = newest
    bvs = process.actions.behaviour(str(new))

    assert len(bvs) == 1
    assert bvs.pop().description is newest


def test_first_actions():
    p1 = Process('x')
    parse_process(p1, '<a> | <b>')
    p1.actions.populate_with_empty_descriptions()
    assert p1.actions.first_actions() == {'a', 'b'}

    p1 = Process('x')
    parse_process(p1, '<a>.<b>')
    p1.actions.populate_with_empty_descriptions()
    assert p1.actions.first_actions() == {'a'}

    p1 = Process('x')
    parse_process(p1, '<a>.<b> | <c>')
    p1.actions.populate_with_empty_descriptions()
    assert p1.actions.first_actions() == {'a', 'c'}

    p1 = Process('x')
    parse_process(p1, '<a> | {b}')
    t = parse_process(p1, '<c>')
    p1.actions.populate_with_empty_descriptions()
    p1.actions['b'].action = t
    assert p1.actions.first_actions() == {'a', 'c'}
    assert p1.actions.first_actions(t) == {'c'}
