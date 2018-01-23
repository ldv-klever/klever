#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
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

from core.vtg.emg.grammars.process import parse_process

__grammar_tests = [
    "([a[2]])",
    "([a].[b]).[c]",
    "([a].[b]) | [c]",
    "[a].[b] | [c]",
    "[a] | [b] | [c]",
    "(([a].[b] | [c]) . [d]) | [e]",
    "[@usb_reset]",
    "<assign>.[register] | <none>",
    "<assign>.[open].(ret_open).[register] | <none>",
    "(!register).[instance_register[%k%]].[instance_deregister[%k%]].(deregister)",
    "(!instance_register).<alloc>.<init>.[probe].(ret_probe).(<probe_success>.((usb_reset).[pre].(ret_pre).[post]."
    "(ret_post) | [suspend].(ret_suspend).[resume].(ret_resume) | <null>).[release].(ret_release) | <failed_probe>)."
    "<free>.(instance_deregister)",
    "[callback].{call} | <positive_probe>.[release].<after_release>.{call} |  <positive_probe>.[suspend].(ret_suspend)."
    "(<suspended>.[resume].(ret_resume) | <not_suspended>).{call} | <negative_probe>.(<free>.(deregister) | [probe]."
    "(ret_probe).{call})"
]

for test in __grammar_tests:
    print(test)
    object = parse_process(test)
    print(str(object))