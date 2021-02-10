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

from klever.core.vtg.emg.common.process import Process
from klever.core.vtg.emg.common.process.parser import parse_process
from klever.core.vtg.emg.common.process.serialization import CollectionEncoder
from klever.core.vtg.emg.common.process.actions import Concatenation, Choice, Parentheses, Subprocess, Dispatch, \
    Receive, Block

def test_detailed_parsing():
    process = Process('test')
    test = "(((a).<b> | [c]) . {d}) | [e]"
    subp = "([f].<g>) | {d}"

    # Parse
    assert parse_process(process, test)
    assert parse_process(process, subp)
    check_parsed_object(process.actions)

    # Then export, import and repeate checks
    #desc = CollectionEncoder._export_process(process)
    #process = Process('test')
    #parse_process(process, desc['process'])
    #check_parsed_object(process.actions)


def check_parsed_object(actions):
    i = actions.initial_action
    pass
    # (((a).<b> | [c]) . {d}) | [e]
    # [e]
    # (((a).<b> | [c]) . {d})
    # ((a).<b> | [c])
    # (a).<b> | [c]
    # (a).<b>
    # (a).<b>
    # (a)
    # <b>
    # [c]
    # {d}
    # ([f].<g>) | {d}
    # ([f].<g>)
    # [f].<g>
    # [f]
    # <g>
    # {d}


def parse_assert(original_method):
    def test_method(*args, **kwargs):
        for test in original_method(*args, **kwargs):
            process = Process('test')
            obj = parse_process(process, test)
            assert obj, f'Cannot parse {test}'

            desc = CollectionEncoder._export_process(process)
            assert desc, f'Cannot export back {test}'
            # todo: implement more careful comparison of strings
            #assert desc.get('process') == test

    return test_method


# @parse_assert
# def test_same_actions():
#     return [
#         "[a].[a]",
#         "(a) | (a)",
#         "[a].[c].[f].{f} | [m].{f}"
#     ]
#
# @parse_assert
# def test_spaces():
#     return [
#         "[c] | ([a].[b])",
#         "[c] | [a].[b]",
#         "[a] | [b] | [c]",
#         "(([a].[b] | [c]) . [d]) | [e]"
#     ]
#
#
# @parse_assert
# def test_pars():
#     return [
#         "([a].[b]).[c]",
#         "([suspend].(<suspended>.[resume] | <not_suspended>) | [port_probe].(<port_probed>.[open].(<opened>.{tty_layer} | <not_opened>.[port_remove]) | <not_port_probed>)).{main_workflow} | [disconnect].[release].{insert_device}"
#     ]
#
#
# @parse_assert
# def test_operators():
#     return [
#         "<free>.(instance_deregister)",
#         "[one].[two]",
#         "[one] | [two]",
#         "<assign>.[register] | <none>",
#         "<assign> | [one].[two]"
#     ]
#
#
# @parse_assert
# def test_multiple_operators():
#     return [
#         "<assign>.[open].(ret_open).[register] | <none>",
#     ]
#
#
# @parse_assert
# def _test_indexes():
#     # todo: unsupported
#     return [
#         "([a[2]])",
#         "(!register).[instance_register[%k%]].[instance_deregister[%k%]].(deregister)"
#     ]
#
#
# @parse_assert
# def test_subprocess():
#     return [
#         "(!instance_register).<alloc>.<init>.[probe1].(ret_probe1).(<probe_success>.((usb_reset).[pre].(ret_pre).[post]."
#         "(ret_post) | [suspend1].(ret_suspend1).[resume1].(ret_resume1) | <null>).[release1].(ret_release)|<failed_probe>)."
#         "[callback].{call}|<positive_probe1>.[release2].<after_release>.{call}| <positive_probe2>.[suspend2].(ret_suspend2)."
#         "(<suspended>.[resume2].(ret_resume2)|<not_suspended>).{call}|<negative_probe>.(<free>.(deregister)|[probe2]."
#         "(ret_probe2).{call})"
#     ]
#
#
# @parse_assert
# def test_broadband_send():
#     return [
#         "[@usb_reset]"
#     ]
