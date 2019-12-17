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

from core.vtg.emg.common.c.types import import_declaration


def parser_test(method):
    def new_method(*args, **kwargs):
        for test in method(*args, **kwargs):
            obj = import_declaration(test)
            # Test that it is parsed
            assert obj

            # Test that it is the same
            new_obj = import_declaration(obj.to_string('name'))
            # todo: Pretty names are different but I am not sure whether it correct or not
            assert obj == new_obj

    return new_method

@parser_test
def test_complex_types():
    return [
        'extern int usb_serial_probe(struct usb_interface *iface, const struct usb_device_id *id)'
    ]


