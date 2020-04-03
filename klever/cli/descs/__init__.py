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

import os

preset_jobs_dir = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__), os.path.pardir, os.path.pardir, os.path.pardir,
        'bridge', 'jobs', 'presets'
    )
)

common_target_program_descs = {
    'Linux': {
        'source code': 'linux-stable',
        'git repository version': 'v3.14.79',
        'configuration': 'allmodconfig',
        'architecture': 'x86_64',
        'model CC options file': 'scripts/mod/empty.c',
        'external modules header files search directory': os.path.join(preset_jobs_dir, 'specifications'),
        'loadable kernel modules': ['all'],
        'allow local source trees use': True,
        'generate makefiles': True,
        'extra headers': [
            'linux/user_namespace.h',
            'linux/tty.h',
            'linux/tty_driver.h',
            'linux/usb.h',
            'linux/usb/serial.h',
            'linux/platform_device.h',
            'linux/netdevice.h',
            'linux/net.h',
            'linux/timer.h',
            'linux/interrupt.h',
            'linux/seq_file.h',
            'linux/i2c.h',
            'linux/mod_devicetable.h',
            'linux/device.h',
            'linux/pm.h',
            'linux/fs.h',
            'linux/rtnetlink.h',
            'net/mac80211.h',
            'linux/iio/iio.h',
            'linux/iio/triggered_buffer.h',
            'linux/cdev.h',
            'linux/miscdevice.h',
            'linux/pci.h',
            'linux/rtc.h',
            'scsi/scsi_host.h',
            'linux/pagemap.h',
            'linux/poll.h',
            'linux/blkdev.h',
            'target/target_core_base.h',
            'target/target_core_backend.h',
            'linux/spi/spi.h',
            'linux/fb.h'
        ],
        'extra Clade options': {
            'Info.extra_CIF_opts': [
                '-D__GNUC__=4',
                '-D__GNUC_MINOR__=6'
            ]
        }
    }
}
