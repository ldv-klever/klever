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

import pytest

from klever.core.vtg.emg.common.c.types import import_declaration
from klever.core.vtg.emg.generators.linuxModule.interface import Container
from klever.core.vtg.emg.generators.linuxModule.interface.collection import InterfaceCollection
from klever.core.vtg.emg.generators.linuxModule.interface.specification import import_interface_declaration


@pytest.fixture
def intf_collection():
    collection = InterfaceCollection()
    usb_driver = Container('usb', 'driver')
    usb_driver.declaration = import_declaration('struct usb_driver driver')
    collection.set_intf(usb_driver)

    return collection


def test_extensions(intf_collection):
    tests = [
        '%usb.driver%',
        '%usb.driver% function(int, void *)',
        'int function(int, void *, %usb.driver%)'
    ]

    for test in tests:
        obj, _ = import_interface_declaration(intf_collection, None, test)
        # Test that it is parsed
        assert obj

        # Test that it is the same
        new_obj, _ = import_interface_declaration(intf_collection, None, obj.to_string('name'))
        # todo: Pretty names are different but I am not sure whether it correct or not
        assert obj == new_obj
