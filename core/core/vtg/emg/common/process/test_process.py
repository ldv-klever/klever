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

from core.vtg.emg.common.process import Process
from core.vtg.emg.common.process.parser import parse_process
from core.vtg.emg.common.process.serialization import CollectionEncoder


def parse_assert(original_method):
    def test_method(*args, **kwargs):
        for test in original_method(*args, **kwargs):
            process = Process('test')
            obj = parse_process(process, test)
            assert obj

            desc = CollectionEncoder._export_process(process)
            assert desc
            # todo: implement more careful comparison of strings
            #assert desc.get('process') == test

    return test_method


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
def _test_indexes():
    # todo: unsupported
    return [
        "([a[2]])",
        "(!register).[instance_register[%k%]].[instance_deregister[%k%]].(deregister)"
    ]


@parse_assert
def test_subprocess():
    return [
        "(!instance_register).<alloc>.<init>.[probe].(ret_probe).(<probe_success>.((usb_reset).[pre].(ret_pre).[post]."
        "(ret_post) | [suspend].(ret_suspend).[resume].(ret_resume) | <null>).[release].(ret_release)|<failed_probe>)."
        "[callback].{call}|<positive_probe>.[release].<after_release>.{call}| <positive_probe>.[suspend].(ret_suspend)."
        "(<suspended>.[resume].(ret_resume)|<not_suspended>).{call}|<negative_probe>.(<free>.(deregister)|[probe]."
        "(ret_probe).{call})"
    ]


@parse_assert
def test_broadband_send():
    return [
        "[@usb_reset]"
    ]
