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

preset_jobs_dir = os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir, 'bridge', 'jobs', 'presets')

common_target_program_descs = {
    'Linux': {
        'source code': 'linux-stable',
        'Git repository version': 'v3.14.79',
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
        ]
    }
}

target_program_descs = [
    # # Testing on loadable Linux kernel modules.
    # {
    #     'build base': 'build bases/linux-3.14.79',
    #     'name': 'Linux',
    #     'Git repository version': 'v3.14.79',
    #     'loadable kernel modules': [
    #         'drivers/ata/pata_arasan_cf.ko',
    #         'drivers/idle/i7300_idle.ko',
    #         'drivers/uwb/hwa-rc.ko'
    #     ]
    # },
    # # Testing on artificial loadable Linux kernel modules.
    # {
    #     'build base': 'build bases/testing/5b3d50',
    #     'name': 'Linux',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'decomposition strategies', 'tests'),
    #     'loadable kernel modules': [
    #         'ext-modules/kernel_library',
    #         'ext-modules/load_order',
    #         'ext-modules/multimodule_error',
    #         'ext-modules/multimodule_false_error',
    #         'ext-modules/several_groups'
    #     ]
    # },
    # {
    #     'build base': 'build bases/testing/6e6e1c',
    #     'name': 'Linux',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'common models', 'tests'),
    #     'loadable kernel modules': [
    #         "ext-modules/linux/drivers/base/dd",
    #         "ext-modules/linux/drivers/spi",
    #         "ext-modules/linux/err",
    #         "ext-modules/linux/ldv/common",
    #         "ext-modules/linux/mm/gfp",
    #         "ext-modules/linux/mm/slab",
    #         "ext-modules/verifier/common",
    #         "ext-modules/verifier/gcc",
    #         "ext-modules/verifier/map",
    #         "ext-modules/verifier/memory",
    #         "ext-modules/verifier/nondet",
    #         "ext-modules/verifier/set/counter",
    #         "ext-modules/verifier/set/flag",
    #         "ext-modules/verifier/set/nonnegative-counter",
    #         "ext-modules/verifier/thread"
    #     ]
    # },
    # {
    #     'build base': 'build bases/testing/455c6f',
    #     'name': 'Linux',
    #     'Git repository version': 'v2.6.33.20',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'environment model specifications',
    #                         'tests'),
    #     'loadable kernel modules': [
    #         'ext-modules/block_device_operations_v.1',
    #         'ext-modules/class_v.1',
    #         'ext-modules/devm_threaded_irq_v.1',
    #         'ext-modules/ethtool_ops_v.1',
    #         'ext-modules/file_operations_v.1',
    #         'ext-modules/get_sb_v.1',
    #         'ext-modules/hid_v.1',
    #         'ext-modules/ieee80211_ops_v.1',
    #         'ext-modules/irq_v.1',
    #         'ext-modules/kthread_v.1',
    #         'ext-modules/net_device_ops_v.1',
    #         'ext-modules/pci_driver_v.1',
    #         'ext-modules/platform_driver_v.1',
    #         'ext-modules/proto_v.1',
    #         'ext-modules/rtc_class_ops_v.1',
    #         'ext-modules/scsi_host_template_v.1',
    #         'ext-modules/seq_operations_v.1',
    #         'ext-modules/serial_core_v.1',
    #         'ext-modules/super_block_v.1',
    #         'ext-modules/tasklet_v.1',
    #         'ext-modules/timer_v.1',
    #         'ext-modules/tty_v.1',
    #         'ext-modules/urb_v.1',
    #         'ext-modules/usb_driver_v.1',
    #         'ext-modules/usb_serial_driver_v.1',
    #         'ext-modules/workqueue_v.1'
    #     ],
    #     'exclude extra headers': [
    #         'linux/iio/iio.h',
    #         'linux/iio/triggered_buffer.h',
    #         'target/target_core_base.h',
    #         'target/target_core_backend.h'
    #     ],
    #     'extra Clade options': {
    #         'Info.extra_CIF_opts': [
    #             '-D__GNUC__=4',
    #             '-D__GNUC_MINOR__=6'
    #         ]
    #     }
    # },
    # {
    #     'build base': 'build bases/testing/fedc1e',
    #     'name': 'Linux',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'environment model specifications',
    #                                      'tests'),
    #     'loadable kernel modules': [
    #         'ext-modules/block_device_operations_v.1',
    #         'ext-modules/class_v.1',
    #         'ext-modules/devm_threaded_irq_v.1',
    #         'ext-modules/ethtool_ops_v.1',
    #         'ext-modules/file_operations_v.1',
    #         'ext-modules/hid_v.1',
    #         'ext-modules/ieee80211_ops_v.1',
    #         'ext-modules/iio_triggered_buffer_v.1',
    #         'ext-modules/irq_v.2',
    #         'ext-modules/kthread_v.1',
    #         'ext-modules/net_device_ops_v.1',
    #         'ext-modules/pci_driver_v.1',
    #         'ext-modules/percpu_irq_v.1',
    #         'ext-modules/platform_driver_v.1',
    #         'ext-modules/proto_v.1',
    #         'ext-modules/rtc_class_ops_v.1',
    #         'ext-modules/scsi_host_template_v.1',
    #         'ext-modules/se_subsystem_api_v.1',
    #         'ext-modules/seq_operations_v.1',
    #         'ext-modules/serial_core_v.1',
    #         'ext-modules/tasklet_v.1',
    #         'ext-modules/timer_v.1',
    #         'ext-modules/tty_v.2',
    #         'ext-modules/urb_v.1',
    #         'ext-modules/usb_driver_v.1',
    #         'ext-modules/usb_serial_driver_v.2',
    #         'ext-modules/workqueue_v.1'
    #     ]
    # },
    # {
    #     'build base': 'build bases/testing/01358e',
    #     'name': 'Linux',
    #     'Git repository version': 'v4.6.7',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'environment model specifications',
    #                                      'tests'),
    #     'loadable kernel modules': [
    #         'ext-modules/block_device_operations_v.1',
    #         'ext-modules/class_v.1',
    #         'ext-modules/devm_threaded_irq_v.1',
    #         'ext-modules/ethtool_ops_v.2',
    #         'ext-modules/file_operations_v.1',
    #         'ext-modules/hid_v.1',
    #         'ext-modules/ieee80211_ops_v.1',
    #         'ext-modules/iio_triggered_buffer_v.1',
    #         'ext-modules/irq_v.2',
    #         'ext-modules/kthread_v.1',
    #         'ext-modules/net_device_ops_v.2',
    #         'ext-modules/pci_driver_v.1',
    #         'ext-modules/percpu_irq_v.1',
    #         'ext-modules/platform_driver_v.1',
    #         'ext-modules/proto_v.2',
    #         'ext-modules/rtc_class_ops_v.1',
    #         'ext-modules/scsi_host_template_v.1',
    #         'ext-modules/seq_operations_v.1',
    #         'ext-modules/serial_core_v.1',
    #         'ext-modules/target_backend_v.1',
    #         'ext-modules/tasklet_v.1',
    #         'ext-modules/timer_v.2',
    #         'ext-modules/tty_v.2',
    #         'ext-modules/urb_v.1',
    #         'ext-modules/usb_driver_v.1',
    #         'ext-modules/usb_serial_driver_v.2',
    #         'ext-modules/workqueue_v.1'
    #     ],
    #     'exclude extra headers': ['linux/poll.h'],
    #     # Linux 4.6.7 can be built with new versions of GCC.
    #     'extra Clade options': {}
    # },
    # {
    #     'build base': 'build bases/testing/a8ec86',
    #     'name': 'Linux',
    #     'Git repository version': 'v4.15.18',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'environment model specifications',
    #                                      'tests'),
    #     'loadable kernel modules': [
    #         'ext-modules/block_device_operations_v.1',
    #         'ext-modules/class_v.1',
    #         'ext-modules/devm_threaded_irq_v.1',
    #         'ext-modules/ethtool_ops_v.3',
    #         'ext-modules/file_operations_v.1',
    #         'ext-modules/hid_v.1',
    #         'ext-modules/ieee80211_ops_v.1',
    #         'ext-modules/iio_triggered_buffer_v.1',
    #         'ext-modules/irq_v.2',
    #         'ext-modules/kthread_v.1',
    #         'ext-modules/net_device_ops_v.2',
    #         'ext-modules/pci_driver_v.2',
    #         'ext-modules/percpu_irq_v.1',
    #         'ext-modules/platform_driver_v.1',
    #         'ext-modules/proto_v.2',
    #         'ext-modules/rtc_class_ops_v.2',
    #         'ext-modules/scsi_host_template_v.2',
    #         'ext-modules/seq_operations_v.1',
    #         'ext-modules/serial_core_v.1',
    #         'ext-modules/target_backend_v.1',
    #         'ext-modules/tasklet_v.2',
    #         'ext-modules/timer_v.3',
    #         'ext-modules/tty_v.2',
    #         'ext-modules/urb_v.1',
    #         'ext-modules/usb_driver_v.1',
    #         'ext-modules/usb_serial_driver_v.2',
    #         'ext-modules/workqueue_v.1'
    #     ],
    #     'exclude extra headers': ['linux/poll.h'],
    #     # Linux 4.15 can be built with new versions of GCC.
    #     'extra Clade options': {}
    # },
    # {
    #     'build base': 'build bases/testing/62134e',
    #     'name': 'Linux',
    #     'Git repository version': 'v4.17.19',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'environment model specifications',
    #                                      'tests'),
    #     'loadable kernel modules': [
    #         'ext-modules/block_device_operations_v.1',
    #         'ext-modules/class_v.1',
    #         'ext-modules/devm_threaded_irq_v.1',
    #         'ext-modules/ethtool_ops_v.3',
    #         'ext-modules/file_operations_v.1',
    #         'ext-modules/hid_v.1',
    #         'ext-modules/ieee80211_ops_v.1',
    #         'ext-modules/iio_triggered_buffer_v.1',
    #         'ext-modules/irq_v.2',
    #         'ext-modules/kthread_v.1',
    #         'ext-modules/net_device_ops_v.2',
    #         'ext-modules/pci_driver_v.2',
    #         'ext-modules/percpu_irq_v.1',
    #         'ext-modules/platform_driver_v.1',
    #         'ext-modules/proto_v.2',
    #         'ext-modules/rtc_class_ops_v.2',
    #         'ext-modules/scsi_host_template_v.2',
    #         'ext-modules/seq_operations_v.1',
    #         'ext-modules/serial_core_v.1',
    #         'ext-modules/target_backend_v.1',
    #         'ext-modules/tasklet_v.2',
    #         'ext-modules/timer_v.3',
    #         'ext-modules/tty_v.2',
    #         'ext-modules/urb_v.1',
    #         'ext-modules/usb_driver_v.1',
    #         'ext-modules/usb_serial_driver_v.2',
    #         'ext-modules/workqueue_v.1'
    #     ],
    #     'exclude extra headers': ['linux/poll.h'],
    #     # Linux 4.17 can be built with new versions of GCC.
    #     'extra Clade options': {}
    # },
    # {
    #     'build base': 'build bases/testing/81b6e0',
    #     'name': 'Linux',
    #     'Git repository version': 'v5.5.9',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'environment model specifications',
    #                                      'tests'),
    #     'loadable kernel modules': [
    #         'ext-modules/block_device_operations_v.1',
    #         'ext-modules/class_v.1',
    #         'ext-modules/devm_threaded_irq_v.1',
    #         'ext-modules/ethtool_ops_v.3',
    #         'ext-modules/file_operations_v.1',
    #         'ext-modules/hid_v.1',
    #         'ext-modules/ieee80211_ops_v.1',
    #         'ext-modules/iio_triggered_buffer_v.1',
    #         'ext-modules/irq_v.2',
    #         'ext-modules/kthread_v.1',
    #         'ext-modules/net_device_ops_v.2',
    #         'ext-modules/pci_driver_v.2',
    #         'ext-modules/percpu_irq_v.1',
    #         'ext-modules/platform_driver_v.1',
    #         'ext-modules/proto_v.2',
    #         'ext-modules/rtc_class_ops_v.2',
    #         'ext-modules/scsi_host_template_v.2',
    #         'ext-modules/seq_operations_v.1',
    #         'ext-modules/serial_core_v.1',
    #         'ext-modules/target_backend_v.1',
    #         'ext-modules/tasklet_v.2',
    #         'ext-modules/timer_v.3',
    #         'ext-modules/tty_v.2',
    #         'ext-modules/urb_v.1',
    #         'ext-modules/usb_driver_v.1',
    #         'ext-modules/usb_serial_driver_v.2',
    #         'ext-modules/workqueue_v.1'
    #     ],
    #     'exclude extra headers': ['linux/poll.h'],
    #     # Linux 5.5 can be built with new versions of GCC.
    #     'extra Clade options': {}
    # },
    # {
    #     'build base': 'build bases/testing/1de383',
    #     'name': 'Linux',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'requirement specifications', 'tests'),
    #     'loadable kernel modules': [
    #         'ext-modules/linux/alloc/irq',
    #         'ext-modules/linux/alloc/spinlock',
    #         'ext-modules/linux/alloc/usb-lock',
    #         'ext-modules/linux/arch/asm/dma-mapping',
    #         'ext-modules/linux/arch/mm/ioremap',
    #         'ext-modules/linux/block/blk-core/queue',
    #         'ext-modules/linux/block/blk-core/request',
    #         'ext-modules/linux/block/genhd',
    #         'ext-modules/linux/concurrency-safety/lock-reduce',
    #         'ext-modules/linux/concurrency-safety/simple',
    #         'ext-modules/linux/concurrency-safety/unsorted',
    #         'ext-modules/linux/drivers/base/class',
    #         'ext-modules/linux/drivers/usb/core/usb/coherent',
    #         'ext-modules/linux/drivers/usb/core/usb/dev',
    #         'ext-modules/linux/drivers/usb/core/driver',
    #         'ext-modules/linux/drivers/usb/core/urb',
    #         'ext-modules/linux/drivers/usb/gadget/udc-core',
    #         'ext-modules/linux/drivers/clk1',
    #         'ext-modules/linux/drivers/clk2',
    #         'ext-modules/linux/empty',
    #         'ext-modules/linux/fs/sysfs/group',
    #         'ext-modules/linux/kernel/locking/mutex',
    #         'ext-modules/linux/kernel/locking/rwlock',
    #         'ext-modules/linux/kernel/locking/spinlock',
    #         'ext-modules/linux/kernel/module',
    #         'ext-modules/linux/kernel/rcu/update/lock',
    #         'ext-modules/linux/kernel/rcu/update/lock-bh',
    #         'ext-modules/linux/kernel/rcu/update/lock-sched',
    #         'ext-modules/linux/kernel/rcu/srcu',
    #         'ext-modules/linux/kernel/sched/completion',
    #         'ext-modules/linux/lib/find_next_bit',
    #         'ext-modules/linux/lib/idr',
    #         'ext-modules/linux/memory-safety',
    #         'ext-modules/linux/net/core/dev',
    #         'ext-modules/linux/net/core/rtnetlink',
    #         'ext-modules/linux/net/core/sock'
    #     ]
    # },
    # {
    #     'build base': 'build bases/testing/1cae6b',
    #     'name': 'Linux',
    #     'configuration': os.path.join(preset_jobs_dir, 'linux', 'testing', 'requirement specifications', 'configs',
    #                                   'no-lockdep'),
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'requirement specifications', 'tests'),
    #     # The only module needs specific kernel configuration for testing.
    #     'loadable kernel modules': ['ext-modules/linux/kernel/sched/completion-no-lockdep']
    # },
    # {
    #     'build base': 'build bases/testing/606cdb',
    #     'name': 'Linux',
    #     'external modules': os.path.join(preset_jobs_dir, 'testing verifiers', 'tests'),
    #     'loadable kernel modules': [
    #         "ext-modules/arrays/one-element",
    #         "ext-modules/arrays/ten-elements",
    #         "ext-modules/arrays/two-dimensional",
    #         "ext-modules/arrays/two-elements",
    #         "ext-modules/bitfields",
    #         "ext-modules/bitwise-operations/and",
    #         "ext-modules/bitwise-operations/complement",
    #         "ext-modules/bitwise-operations/left-shift",
    #         "ext-modules/bitwise-operations/or",
    #         "ext-modules/bitwise-operations/right-shift",
    #         "ext-modules/bitwise-operations/xor",
    #         "ext-modules/casts",
    #         "ext-modules/conditions/dangling-else",
    #         "ext-modules/conditions/if",
    #         "ext-modules/conditions/if-else",
    #         "ext-modules/conditions/if-else-if",
    #         "ext-modules/conditions/if-else-if-else",
    #         "ext-modules/conditions/nested",
    #         "ext-modules/conditions/ternary-operator",
    #         "ext-modules/dynamic-memory/xmalloc",
    #         "ext-modules/dynamic-memory/xmalloc-data",
    #         "ext-modules/dynamic-memory/xzalloc",
    #         "ext-modules/enumerations",
    #         "ext-modules/function-pointers",
    #         "ext-modules/gotos",
    #         "ext-modules/inline-assembler",
    #         "ext-modules/integers/binary-minus",
    #         "ext-modules/integers/binary-plus",
    #         "ext-modules/integers/division",
    #         "ext-modules/integers/multiplication",
    #         "ext-modules/integers/remainder",
    #         "ext-modules/integers/unary-minus",
    #         "ext-modules/integers/unary-plus",
    #         "ext-modules/inter-functional-analysis/one-level",
    #         "ext-modules/inter-functional-analysis/ten-levels",
    #         "ext-modules/inter-functional-analysis/two-levels",
    #         "ext-modules/lists",
    #         "ext-modules/logical-operations/and",
    #         "ext-modules/logical-operations/not",
    #         "ext-modules/logical-operations/or",
    #         "ext-modules/loops/break",
    #         "ext-modules/loops/continue",
    #         "ext-modules/loops/do-while",
    #         "ext-modules/loops/nested",
    #         "ext-modules/loops/one-iteration",
    #         "ext-modules/loops/ten-iterations",
    #         "ext-modules/loops/two-iterations",
    #         "ext-modules/loops/while",
    #         "ext-modules/pointers/address",
    #         "ext-modules/pointers/alias",
    #         "ext-modules/pointers/container-of",
    #         "ext-modules/pointers/dereference",
    #         "ext-modules/pointers/null",
    #         "ext-modules/recursion/one-depth",
    #         "ext-modules/recursion/ten-depth",
    #         "ext-modules/recursion/two-depth",
    #         "ext-modules/relational-operations/equal",
    #         "ext-modules/relational-operations/greater",
    #         "ext-modules/relational-operations/greater-or-equal",
    #         "ext-modules/relational-operations/less",
    #         "ext-modules/relational-operations/less-or-equal",
    #         "ext-modules/relational-operations/not-equal",
    #         "ext-modules/sizeof",
    #         "ext-modules/structures/no-nesting",
    #         "ext-modules/structures/one-nesting",
    #         "ext-modules/structures/ten-nesting",
    #         "ext-modules/switches/break",
    #         "ext-modules/switches/default",
    #         "ext-modules/switches/one-case",
    #         "ext-modules/switches/ten-cases",
    #         "ext-modules/switches/two-cases",
    #         "ext-modules/unions/no-nesting",
    #         "ext-modules/unions/one-nesting",
    #         "ext-modules/unions/same-memory",
    #         "ext-modules/unions/ten-nesting",
    #         "ext-modules/variables/assignment",
    #         "ext-modules/variables/bitwise-and-assignment",
    #         "ext-modules/variables/bitwise-or-assignment",
    #         "ext-modules/variables/bitwise-xor-assignment",
    #         "ext-modules/variables/division-assignment",
    #         "ext-modules/variables/left-shift-assignment",
    #         "ext-modules/variables/minus-assignment",
    #         "ext-modules/variables/multiplication-assignment",
    #         "ext-modules/variables/plus-assignment",
    #         "ext-modules/variables/postfix-decrement",
    #         "ext-modules/variables/postfix-increment",
    #         "ext-modules/variables/prefix-decrement",
    #         "ext-modules/variables/prefix-increment",
    #         "ext-modules/variables/remainder-assignment",
    #         "ext-modules/variables/right-shift-assignment"
    #     ]
    # },
    # # Validation on commits in Linux kernel Git repositories.
    # {
    #     'build base': 'build bases/validation/7ce77510c9c7~',
    #     'name': 'Linux',
    #     'Git repository version': '7ce77510c9c7~',
    #     'loadable kernel modules': ['drivers/usb/serial/opticon.ko'],
    #     'exclude extra headers': [
    #         'linux/iio/iio.h',
    #         'linux/iio/triggered_buffer.h',
    #         'target/target_core_backend.h'
    #     ]
    # },
    # {
    #     'build base': 'build bases/validation/7ce77510c9c7',
    #     'name': 'Linux',
    #     'Git repository version': '7ce77510c9c7',
    #     'loadable kernel modules': ['drivers/usb/serial/opticon.ko'],
    #     'exclude extra headers': [
    #         'linux/iio/iio.h',
    #         'linux/iio/triggered_buffer.h',
    #         'target/target_core_backend.h'
    #     ]
    # },
    # {
    #     'build base': 'build bases/validation/60b35930067d~',
    #     'name': 'Linux',
    #     'Git repository version': '60b35930067d~',
    #     'loadable kernel modules': ['drivers/media/usb/dvb-usb/dvb-usb-cxusb.ko']
    # },
    # {
    #     'build base': 'build bases/validation/60b35930067d',
    #     'name': 'Linux',
    #     'Git repository version': '60b35930067d',
    #     'loadable kernel modules': ['drivers/media/usb/dvb-usb/dvb-usb-cxusb.ko']
    # },
    # {
    #     'build base': 'build bases/validation/214c97a12f1f',
    #     'name': 'Linux',
    #     'Git repository version': '214c97a12f1f',
    #     'loadable kernel modules': ['drivers/media/usb/usbvision/usbvision.ko']
    # },
    # {
    #     'build base': 'build bases/validation/214c97a12f1f~',
    #     'name': 'Linux',
    #     'Git repository version': '214c97a12f1f~',
    #     'loadable kernel modules': ['drivers/media/usb/usbvision/usbvision.ko']
    # },
    # {
    #     'build base': 'build bases/validation/e4c7f259c5be~',
    #     'name': 'Linux',
    #     'Git repository version': 'e4c7f259c5be~',
    #     'loadable kernel modules': ['drivers/net/usb/kaweth.ko'],
    #     'exclude extra headers': ['linux/iio/triggered_buffer.h']
    # },
    # {
    #     'build base': 'build bases/validation/e4c7f259c5be',
    #     'name': 'Linux',
    #     'Git repository version': 'e4c7f259c5be',
    #     'loadable kernel modules': ['drivers/net/usb/kaweth.ko'],
    #     'exclude extra headers': ['linux/iio/triggered_buffer.h']
    # },
    # {
    #     'build base': 'build bases/validation/448356262f56~',
    #     'name': 'Linux',
    #     'Git repository version': '448356262f56~',
    #     'loadable kernel modules': ['drivers/usb/serial/kobil_sct.ko']
    # },
    # {
    #     'build base': 'build bases/validation/448356262f56',
    #     'name': 'Linux',
    #     'Git repository version': '448356262f56',
    #     'loadable kernel modules': ['drivers/usb/serial/kobil_sct.ko']
    # },
    # {
    #     'build base': 'build bases/validation/d8e172f3c0a5',
    #     'name': 'Linux',
    #     'Git repository version': 'd8e172f3c0a5',
    #     'loadable kernel modules': ['drivers/spi/spi-imx.ko']
    # },
    # {
    #     'build base': 'build bases/validation/d8e172f3c0a5~',
    #     'name': 'Linux',
    #     'Git repository version': 'd8e172f3c0a5~',
    #     'loadable kernel modules': ['drivers/spi/spi-imx.ko']
    # },
    # {
    #     'build base': 'build bases/validation/bff71889260f~',
    #     'name': 'Linux',
    #     'Git repository version': 'bff71889260f~',
    #     'loadable kernel modules': ['drivers/staging/iio/adc/mxs-lradc.ko']
    # },
    # {
    #     'build base': 'build bases/validation/bff71889260f',
    #     'name': 'Linux',
    #     'Git repository version': 'bff71889260f',
    #     'loadable kernel modules': ['drivers/staging/iio/adc/mxs-lradc.ko']
    # },
    # {
    #     'build base': 'build bases/validation/2ba4b92e8773~',
    #     'name': 'Linux',
    #     'Git repository version': '2ba4b92e8773~',
    #     'loadable kernel modules': ['drivers/usb/dwc2/dwc2_gadget.ko']
    # },
    # {
    #     'build base': 'build bases/validation/2ba4b92e8773',
    #     'name': 'Linux',
    #     'Git repository version': '2ba4b92e8773',
    #     'loadable kernel modules': ['drivers/usb/dwc2/dwc2_gadget.ko']
    # },
    # {
    #     'build base': 'build bases/validation/c822fb57ba12~',
    #     'name': 'Linux',
    #     'Git repository version': 'c822fb57ba12~',
    #     'loadable kernel modules': ['drivers/spi/spi-pxa2xx-platform.ko']
    # },
    # {
    #     'build base': 'build bases/validation/c822fb57ba12',
    #     'name': 'Linux',
    #     'Git repository version': 'c822fb57ba12',
    #     'loadable kernel modules': ['drivers/spi/spi-pxa2xx-platform.ko']
    # },
    # {
    #     'build base': 'build bases/validation/5c256d215753~',
    #     'name': 'Linux',
    #     'Git repository version': '5c256d215753~',
    #     'loadable kernel modules': ['drivers/media/usb/dvb-usb/dvb-usb-dw2102.ko']
    # },
    # {
    #     'build base': 'build bases/validation/5c256d215753',
    #     'name': 'Linux',
    #     'Git repository version': '5c256d215753',
    #     'loadable kernel modules': ['drivers/media/usb/dvb-usb/dvb-usb-dw2102.ko']
    # },
    # {
    #     'build base': 'build bases/validation/790cc82a2b2b~',
    #     'name': 'Linux',
    #     'Git repository version': '790cc82a2b2b~',
    #     'loadable kernel modules': ['drivers/input/misc/arizona-haptics.ko']
    # },
    # {
    #     'build base': 'build bases/validation/790cc82a2b2b',
    #     'name': 'Linux',
    #     'Git repository version': '790cc82a2b2b',
    #     'loadable kernel modules': ['drivers/input/misc/arizona-haptics.ko']
    # },
    # {
    #     'build base': 'build bases/validation/ae3f34854485~',
    #     'name': 'Linux',
    #     'Git repository version': 'ae3f34854485~',
    #     'loadable kernel modules': ['fs/nfs/nfs.ko']
    # },
    # {
    #     'build base': 'build bases/validation/ae3f34854485',
    #     'name': 'Linux',
    #     'Git repository version': 'ae3f34854485',
    #     'loadable kernel modules': ['fs/nfs/nfs.ko']
    # },
    # {
    #     'build base': 'build bases/validation/44f694330e1e~',
    #     'name': 'Linux',
    #     'Git repository version': '44f694330e1e~',
    #     'loadable kernel modules': ['net/sunrpc/sunrpc.ko']
    # },
    # {
    #     'build base': 'build bases/validation/44f694330e1e',
    #     'name': 'Linux',
    #     'Git repository version': '44f694330e1e',
    #     'loadable kernel modules': ['net/sunrpc/sunrpc.ko']
    # },
    # {
    #     'build base': 'build bases/validation/21a018a58f3c~',
    #     'name': 'Linux',
    #     'Git repository version': '21a018a58f3c~',
    #     'loadable kernel modules': ['net/tipc/tipc.ko']
    # },
    # {
    #     'build base': 'build bases/validation/21a018a58f3c',
    #     'name': 'Linux',
    #     'Git repository version': '21a018a58f3c',
    #     'loadable kernel modules': ['net/tipc/tipc.ko']
    # },
    # {
    #     'build base': 'build bases/validation/ac4de081312a~',
    #     'name': 'Linux',
    #     'Git repository version': 'ac4de081312a~',
    #     'loadable kernel modules': [
    #         'drivers/leds/leds-lp55xx-common.ko',
    #         'drivers/leds/leds-lp5523.ko',
    #         'drivers/leds/leds-lp5521.ko'
    #     ]
    # },
    # {
    #     'build base': 'build bases/validation/ac4de081312a',
    #     'name': 'Linux',
    #     'Git repository version': 'ac4de081312a',
    #     'loadable kernel modules': [
    #         'drivers/leds/leds-lp55xx-common.ko',
    #         'drivers/leds/leds-lp5523.ko',
    #         'drivers/leds/leds-lp5521.ko'
    #     ]
    # },
    # {
    #     'build base': 'build bases/validation/063579d4c3ed~',
    #     'name': 'Linux',
    #     'Git repository version': '063579d4c3ed~',
    #     'loadable kernel modules': [
    #         'drivers/w1/wire.ko',
    #         'drivers/w1/masters/ds2482.ko'
    #     ]
    # },
    # {
    #     'build base': 'build bases/validation/063579d4c3ed',
    #     'name': 'Linux',
    #     'Git repository version': '063579d4c3ed',
    #     'loadable kernel modules': [
    #         'drivers/w1/wire.ko',
    #         'drivers/w1/masters/ds2482.ko'
    #     ]
    # },
    # {
    #     'build base': 'build bases/validation/9aaf9678ea3e~',
    #     'name': 'Linux',
    #     'Git repository version': '9aaf9678ea3e~',
    #     'loadable kernel modules': [
    #         'sound/pci/emu10k1/snd-emu10k1.ko',
    #         'sound/pci/emu10k1/snd-emu10k1-synth.ko'
    #     ],
    #     'exclude extra headers': [
    #         'linux/iio/iio.h',
    #         'linux/iio/triggered_buffer.h',
    #         'target/target_core_backend.h'
    #     ]
    # },
    # {
    #     'build base': 'build bases/validation/9aaf9678ea3e',
    #     'name': 'Linux',
    #     'Git repository version': '9aaf9678ea3e',
    #     'loadable kernel modules': [
    #         'sound/pci/emu10k1/snd-emu10k1.ko',
    #         'sound/pci/emu10k1/snd-emu10k1-synth.ko'
    #     ],
    #     'exclude extra headers': [
    #         'linux/iio/iio.h',
    #         'linux/iio/triggered_buffer.h',
    #         'target/target_core_backend.h'
    #     ]
    # }
]

# TODO: Unsupported tests.
unsupported_target_program_descs = [
    # {
    #     'build base': 'build bases/testing/57d7f5',
    #     'name': 'Linux',
    #     'Git repository version': 'v4.15.18',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'environment model specs', 'tests'),
    #     'loadable kernel modules': [
    #         'ext-modules/block_device_operations_v.1',
    #         'ext-modules/class_v.1',
    #         'ext-modules/devm_threaded_irq_v.1',
    #         'ext-modules/ethtool_ops_v.2',
    #         'ext-modules/file_operations_v.1',
    #         'ext-modules/hid_v.1',
    #         'ext-modules/ieee80211_ops_v.1',
    #         'ext-modules/iio_triggered_buffer_v.1',
    #         'ext-modules/irq_v.2',
    #         'ext-modules/net_device_ops_v.2',
    #         'ext-modules/pci_driver_v.1',
    #         'ext-modules/percpu_irq_v.1',
    #         'ext-modules/platform_driver_v.1',
    #         'ext-modules/proto_v.2',
    #         'ext-modules/rtc_class_ops_v.1',
    #         'ext-modules/scsi_host_template_v.1',
    #         'ext-modules/seq_operations_v.1',
    #         'ext-modules/serial_core_v.1',
    #         'ext-modules/target_backend_v.1',
    #         'ext-modules/tty_v.2',
    #         'ext-modules/usb_driver_v.1',
    #         'ext-modules/usb_serial_driver_v.2',
    #         'ext-modules/timer_v.3',
    #         'ext-modules/workqueue_v.1',
    #         'ext-modules/urb_v.1',
    #         'ext-modules/tasklet_v.2',
    #         'ext-modules/kthread_v.1'
    #     ],
    #     'exclude extra headers': ['linux/poll.h'],
    #     # Linux 4.15.18 can be built with new versions of GCC.
    #     'extra Clade options': {}
    # },
    # {
    #     'build base': 'build bases/testing/7a7e7e',
    #     'name': 'Linux',
    #     'Git repository version': 'v4.17.19',
    #     'external modules': os.path.join(preset_jobs_dir, 'linux', 'testing', 'environment model specs', 'tests'),
    #     'loadable kernel modules': [
    #         'ext-modules/block_device_operations_v.1',
    #         'ext-modules/class_v.1',
    #         'ext-modules/devm_threaded_irq_v.1',
    #         'ext-modules/ethtool_ops_v.2',
    #         'ext-modules/file_operations_v.1',
    #         'ext-modules/hid_v.1',
    #         'ext-modules/ieee80211_ops_v.1',
    #         'ext-modules/iio_triggered_buffer_v.1',
    #         'ext-modules/irq_v.2',
    #         'ext-modules/net_device_ops_v.2',
    #         'ext-modules/pci_driver_v.1',
    #         'ext-modules/percpu_irq_v.1',
    #         'ext-modules/platform_driver_v.1',
    #         'ext-modules/proto_v.2',
    #         'ext-modules/rtc_class_ops_v.1',
    #         'ext-modules/scsi_host_template_v.1',
    #         'ext-modules/seq_operations_v.1',
    #         'ext-modules/serial_core_v.1',
    #         'ext-modules/target_backend_v.1',
    #         'ext-modules/tty_v.2',
    #         'ext-modules/usb_driver_v.1',
    #         'ext-modules/usb_serial_driver_v.2',
    #         'ext-modules/timer_v.3',
    #         'ext-modules/workqueue_v.1',
    #         'ext-modules/urb_v.1',
    #         'ext-modules/tasklet_v.2',
    #         'ext-modules/kthread_v.1'
    #     ],
    #     'exclude extra headers': ['linux/poll.h'],
    #     # Linux v4.17.19 can be built with new versions of GCC.
    #     'extra Clade options': {}
    # }
]
