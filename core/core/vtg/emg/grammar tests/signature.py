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

from core.vtg.emg.common.c.types import import_declaration

__grammar_tests = [
    "int _prf(int (*func)())",
    "static int func(int, void (*)(void))",
    "static int (*func)(int, void (*)(void))",
    "static int (*func [])(int, void (*)(void))",
    "static int a;",
    "int ** a(int **(*(*arg))(void))",
    "struct {   struct file *file;   struct page *page;   struct dir_context *ctx;   long unsigned int page_index;   u64 *dir_cookie;   u64 last_cookie;   loff_t current_index;   decode_dirent_t decode;   long unsigned int timestamp;   long unsigned int gencount;   unsigned int cache_entry_index;   unsigned char plus : 1;   unsigned char eof : 1; } nfs_readdir_descriptor_t",
    'union {   void *arg;   struct kparam_string const *str;   struct kparam_array const *arr; }',
    'union {   s64 lock;    } arch_rwlock_t',
    'union {   s64 lock;   struct   {     u32 read;     s32 write;   }; } arch_rwlock_t',
    'struct { short unsigned int size; short unsigned int byte_cnt; short unsigned int threshold; } SR9800_BULKIN_SIZE[8U]',
    'unsigned char disable_hub_initiated_lpm : 1',
    'int a',
    'int a;',
    'int a:1',
    'int a:1;',
    'int a[6U]',
    'int int_a',
    'static int a',
    'static const int a',
    'static int const a',
    'int * a',
    'int ** a',
    'int * const a',
    'int * const * a',
    'int * const ** a',
    'int ** const ** a',
    'struct usb a',
    'const struct usb a',
    'const struct usb * a',
    'struct usb * const a',
    'union usb * const a',
    'mytypedef * a',
    'int a []',
    'int a [1]',
    'int a [const 1]',
    'int a [*]',
    'int a [const *]',
    'int a [const *][1]',
    'int a [const *][1][]',
    'static struct usb ** a [const 1][2][*]',
    'int (a)',
    'int *(*a)',
    'int *(**a)',
    'int *(* const a [])',
    'int *(* const a) []',
    'int *(* const a []) [*]',
    'int *(*(a))',
    'int (*(*(a) [])) []',
    'int (*(*(*(a) []))) []',
    'int a(int)',
    'int a(int, int)',
    'int a(void)',
    'void a(void)',
    'void a(int, ...)',
    'void (*a) (int, ...)',
    "int func(int, void (*)(void))",
    "int func(void (*)(void), int)",
    "int func(int, int (*)(int))",
    "int func(int, void (*)(void *))",
    "int func(int *, void (*)(void))",
    "int func(int, int (*)(int))",
    "int func(int *, int (*)(int, int))",
    "int func(int *, int (*)(int, int), ...)",
    "int (*f)(int *)",
    "int (*f)(int *, int *)",
    "int func(struct nvme_dev *, void *)",
    "int (*f)(struct nvme_dev *, void *)",
    "void (**a)(struct nvme_dev *, void *)",
    "void (**a)",
    "void func(struct nvme_dev *, void *, struct nvme_completion *)",
    "void (**a)(void)",
    "void (**a)(struct nvme_dev * a)",
    "void (**a)(struct nvme_dev * a, int)",
    "void (**a)(struct nvme_dev * a, void * a)",
    "void (**a)(struct nvme_dev *, void *)",
    "void (**a)(struct nvme_dev *, void *, struct nvme_completion *)",
    "void (**a)(struct nvme_dev *, void *, int (*)(void))",
    "int func(int (*)(int))",
    "int func(int (*)(int *), ...)",
    "int func(int (*)(int, ...))",
    "int func(int (*)(int, ...), ...)",
    "int (*a)(int (*)(int, ...), ...)",
    'void (*((*a)(int, ...)) []) (void) []',
    '%usb.driver%',
    '$ my_function($, %usb.driver%, int)',
    '%usb.driver% function(int, void *)',
    '%usb.driver% function(int, $, %usb.driver%)'
]

for test in __grammar_tests:
    print(test)
    object = import_declaration(test)
    #print(object.pretty_name)
    print(object.identifier)
    print(object.to_string('a'))