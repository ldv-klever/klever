# Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

# TODO: Unsupported tests.
unsupported_descs = [
    {
        'build base': 'testing/57d7f5',
        'name': 'Linux',
        'git repository version': 'v4.15.18',
        'external modules': 'linux/testing/environment model specs/tests',
        'loadable kernel modules': [
            'ext-modules/block_device_operations_v.1',
            'ext-modules/class_v.1',
            'ext-modules/devm_threaded_irq_v.1',
            'ext-modules/ethtool_ops_v.2',
            'ext-modules/file_operations_v.1',
            'ext-modules/hid_v.1',
            'ext-modules/ieee80211_ops_v.1',
            'ext-modules/iio_triggered_buffer_v.1',
            'ext-modules/irq_v.2',
            'ext-modules/net_device_ops_v.2',
            'ext-modules/pci_driver_v.1',
            'ext-modules/percpu_irq_v.1',
            'ext-modules/platform_driver_v.1',
            'ext-modules/proto_v.2',
            'ext-modules/rtc_class_ops_v.1',
            'ext-modules/scsi_host_template_v.1',
            'ext-modules/seq_operations_v.1',
            'ext-modules/serial_core_v.1',
            'ext-modules/target_backend_v.1',
            'ext-modules/tty_v.2',
            'ext-modules/usb_driver_v.1',
            'ext-modules/usb_serial_driver_v.2',
            'ext-modules/timer_v.3',
            'ext-modules/workqueue_v.1',
            'ext-modules/urb_v.1',
            'ext-modules/tasklet_v.2',
            'ext-modules/kthread_v.1'
        ],
        'exclude extra headers': ['linux/poll.h'],
        # Linux 4.15.18 can be built with new versions of GCC.
        'extra Clade options': {}
    },
    {
        'build base': 'testing/7a7e7e',
        'name': 'Linux',
        'git repository version': 'v4.17.19',
        'external modules': 'linux/testing/environment model specs/tests',
        'loadable kernel modules': [
            'ext-modules/block_device_operations_v.1',
            'ext-modules/class_v.1',
            'ext-modules/devm_threaded_irq_v.1',
            'ext-modules/ethtool_ops_v.2',
            'ext-modules/file_operations_v.1',
            'ext-modules/hid_v.1',
            'ext-modules/ieee80211_ops_v.1',
            'ext-modules/iio_triggered_buffer_v.1',
            'ext-modules/irq_v.2',
            'ext-modules/net_device_ops_v.2',
            'ext-modules/pci_driver_v.1',
            'ext-modules/percpu_irq_v.1',
            'ext-modules/platform_driver_v.1',
            'ext-modules/proto_v.2',
            'ext-modules/rtc_class_ops_v.1',
            'ext-modules/scsi_host_template_v.1',
            'ext-modules/seq_operations_v.1',
            'ext-modules/serial_core_v.1',
            'ext-modules/target_backend_v.1',
            'ext-modules/tty_v.2',
            'ext-modules/usb_driver_v.1',
            'ext-modules/usb_serial_driver_v.2',
            'ext-modules/timer_v.3',
            'ext-modules/workqueue_v.1',
            'ext-modules/urb_v.1',
            'ext-modules/tasklet_v.2',
            'ext-modules/kthread_v.1'
        ],
        'exclude extra headers': ['linux/poll.h'],
        # Linux v4.17.19 can be built with new versions of GCC.
        'extra Clade options': {}
    }
]
