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

from klever.core.vtg.emg.common.process import Process
from klever.core.vtg.emg.common.process.parser import parse_process
from klever.core.vtg.emg.common.process.serialization import CollectionEncoder
from klever.core.vtg.emg.common.process.actions import Concatenation, Choice, Parentheses, Subprocess, Dispatch, \
    Receive, Block, Operator


def test_detailed_parsing():
    process = Process('test')
    test = "(((a).<b> | [c]) . {d}) | [e]"
    subp = "([f].<g>) | {d}"

    # Parse
    assert parse_process(process, test)
    next_action = parse_process(process, subp)
    assert next_action
    process.actions['d'] = Subprocess('d')
    process.actions['d'].action = next_action
    check_parsed_object(process.actions)

    # Then export, import and repeat checks
    desc = CollectionEncoder()._serialize_process(process)
    process = Process('test')
    assert parse_process(process, desc['process'])
    next_action = parse_process(process, desc['actions']['d']['process'])
    assert next_action
    process.actions['d'] = Subprocess('d')
    process.actions['d'].action = next_action
    check_parsed_object(process.actions)


def check_parsed_object(actions):
    def expect(action, kind, length=None):
        if isinstance(action, Operator):
            assert isinstance(action, kind), f"Got {repr(action)} instead of {kind.__name__}"
        else:
            assert action.kind is kind, f"Got {repr(action.kind)} instead of {kind.__name__}"

        assert length is None or len(action) == length, f'Got length {len(action)} instead of {length} for ' \
                                                        f'{repr(action)}'

    i = actions.initial_action
    expect(i, Concatenation, 1)
    c1 = i[0]
    # (((a).<b> | [c]) . {d}) | [e]
    expect(c1, Choice, 2)

    c1, c2 = c1
    c1 = c1[0] # Concatenation
    c2 = c2[0] # Concatenation
    if not isinstance(c1, Parentheses):
        c1, c2 = c2, c1

    # [e]
    expect(c2, Dispatch)

    # (((a).<b> | [c]) . {d})
    expect(c1, Parentheses)
    c1 = c1[0]

    # ((a).<b> | [c]) . {d}
    expect(c1, Concatenation, 2)
    c1, c2 = c1

    # {d}
    expect(c2, Subprocess)

    # ((a).<b> | [c])
    expect(c1, Parentheses)
    c1 = c1[0]

    # (a).<b> | [c]
    expect(c1, Choice, 2)
    c1, c2 = c1
    if isinstance(c2, Concatenation) and len(c2) == 2:
        c2, c1 = c1, c2

    # [c]
    if isinstance(c2, Concatenation):
        # This is allowed
        expect(c2, Concatenation, 1)
        c2 = c2[0]
    expect(c2, Dispatch)

    # (a).<b>
    expect(c1, Concatenation, 2)
    c1, c2 = c1
    expect(c1, Receive)
    expect(c2, Block)

    subp = actions['d'].action
    expect(subp, Concatenation, 1)
    c1 = subp[0]
    # ([f].<g>) | {d}
    expect(c1, Choice, 2)
    c1, c2 = c1
    if isinstance(c1, Concatenation) and isinstance(c2, Concatenation):
        c1 = c1[0]
        c2 = c2[0]

    if isinstance(c2, Parentheses):
        c2, c1 = c1, c2

    # {d}
    expect(c2, Subprocess)

    # ([f].<g>)
    expect(c1, Parentheses)
    c1 = c1[0]

    # [f].<g>
    expect(c1, Concatenation, 2)
    c1, c2 = c1
    expect(c1, Dispatch)
    expect(c2, Block)


def parse_assert(original_method):
    def test_method(*args, **kwargs):
        for test in original_method(*args, **kwargs):
            process = Process('test')
            obj = parse_process(process, test)
            assert obj, f'Cannot parse {test}'

    return test_method


@parse_assert
def test_same_actions():
    return [
        "[a].[a]",
        "(a) | (a)",
        "[a].[c].[f].{f} | [m].{f}"
    ]

@parse_assert
def test_spaces():
    return [
        "[c] | ([a].[b])",
        "[c] | [a].[b]",
        "[a] | [b] | [c]",
        "(([a].[b] | [c]) . [d]) | [e]"
    ]


@parse_assert
def test_pars():
    return [
        "([a].[b]).[c]",
        "([suspend].(<suspended>.[resume] | <not_suspended>) | [port_probe].(<port_probed>.[open].(<opened>.{tty_layer} | <not_opened>.[port_remove]) | <not_port_probed>)).{main_workflow} | [disconnect].[release].{insert_device}"
    ]


@parse_assert
def test_operators():
    return [
        "<free>.(instance_deregister)",
        "[one].[two]",
        "[one] | [two]",
        "<assign>.[register] | <none>",
        "<assign> | [one].[two]"
    ]


@parse_assert
def test_multiple_operators():
    return [
        "<assign>.[open].(ret_open).[register] | <none>",
    ]


@parse_assert
def test_indexes():
    return [
        "[a[2]]",
        "(a[2])",
        "<a[2]>",
        "{jump[5]}",
        "([a[2]])",
        "(!register).[instance_register[%k%]].[instance_deregister[%k%]].(deregister)",
        "(!register).{jump[%k%]}"
    ]


@parse_assert
def test_subprocess():
    return [
        "(!instance_register).<alloc>.<init>.[probe1].(ret_probe1).(<probe_success>.((usb_reset).[pre].(ret_pre).[post]."
        "(ret_post) | [suspend1].(ret_suspend1).[resume1].(ret_resume1) | <null>).[release1].(ret_release)|<failed_probe>)."
        "[callback].{call}|<positive_probe1>.[release2].<after_release>.{call}| <positive_probe2>.[suspend2].(ret_suspend2)."
        "(<suspended>.[resume2].(ret_resume2)|<not_suspended>).{call}|<negative_probe>.(<free>.(deregister)|[probe2]."
        "(ret_probe2).{call})"
    ]


@parse_assert
def test_broadband_send():
    return [
        "[@usb_reset]"
    ]
