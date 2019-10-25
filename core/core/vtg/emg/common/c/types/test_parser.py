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


class TestCParser:

    def _parser_test(method):
        def new_method(self, *args, **kwargs):
            for test in method(self, *args, **kwargs):
                obj = import_declaration(test)
                # Test that it is parsed
                assert obj

                # Test that it is the same
                new_obj = import_declaration(obj.to_string('name'))
                assert new_obj.pretty_name == obj.pretty_name

        return new_method

    @_parser_test
    def test_var(self):
        return [
            'int a',
            'int a;',
            'static int a;'
        ]

    @_parser_test
    def test_pars(self):
        return [
            'int (a)',
            'int *(*a)',
            'int *(**a)',
            'int *(* const a [])',
            'int *(* const a) []',
            'int *(* const a []) [*]',
            'int *(*(a))',
            'int (*(*(a) [])) []',
            'int (*(*(*(a) []))) []',
            'void (**a)'
        ]

    @_parser_test
    def test_bit_fields(self):
        return [
            'int a:1',
            'int a:1;',
            'unsigned char disable_hub_initiated_lpm : 1'
        ]

    @_parser_test
    def test_arrays(self):
        return [
            'int a[6U]'
        ]

    @_parser_test
    def test_tricky_names(self):
        return [
            'int int_a'
        ]

    @_parser_test
    def test_complex_types(self):
        return [
            'static int a',
            'static const int a',
            'static int const a'
        ]

    @_parser_test
    def test_pointers(self):
        return [
            'int * a',
            'int ** a',
            'int * const a',
            'int * const * a',
            'int * const ** a',
            'int ** const ** a'
        ]

    @_parser_test
    def test_tructs(self):
        return [
            'struct usb a',
            'const struct usb a',
            'const struct usb * a',
            'struct usb * const a',
        ]

    @_parser_test
    def test_nameless_structs(self):
        return [
            "struct {   struct file *file;   struct page *page;   struct dir_context *ctx;   long unsigned int page_index;   u64 *dir_cookie;   u64 last_cookie;   loff_t current_index;   decode_dirent_t decode;   long unsigned int timestamp;   long unsigned int gencount;   unsigned int cache_entry_index;   unsigned char plus : 1;   unsigned char eof : 1; } nfs_readdir_descriptor_t",
            "struct { short unsigned int size; short unsigned int byte_cnt; short unsigned int threshold; } SR9800_BULKIN_SIZE[8U]"
        ]

    @_parser_test
    def test_unions(self):
        return [
            'union usb * const a'
        ]

    @_parser_test
    def test_nameless_unions(self):
        return [
            'union {   void *arg;   struct kparam_string const *str;   struct kparam_array const *arr; }',
            'union {   s64 lock;    } arch_rwlock_t',
            'union {   s64 lock;   struct   {     u32 read;     s32 write;   }; } arch_rwlock_t'
        ]

    @_parser_test
    def test_typedefs(self):
        return [
            'mytypedef * a'
        ]

    @_parser_test
    def test_matrix(self):
        return [
            'int a []',
            'int a [1]',
            'int a [const 1]',
            'int a [*]',
            'int a [const *]',
            'int a [const *][1]',
            'int a [const *][1][]',
            'static struct usb ** a [const 1][2][*]'
        ]

    @_parser_test
    def test_functions(self):
        return [
            'int a(int)',
            'int a(int, int)',
            'int a(void)',
            'void a(void)',
            'void a(int, ...)',
            'int func(struct nvme_dev *, void *)',
            'void func(struct nvme_dev *, void *, struct nvme_completion *)'
        ]

    @_parser_test
    def test_function_pointers(self):
        return [
            "void (*a) (int, ...)",
            "int (*f)(int *)",
            "int (*f)(int *, int *)",
            "int (*f)(struct nvme_dev *, void *)",
            "void (**a)(struct nvme_dev *, void *)",
            "void (**a)(void)",
            "void (**a)(struct nvme_dev * a)",
            "void (**a)(struct nvme_dev * a, int)",
            "void (**a)(struct nvme_dev * a, void * a)",
            "void (**a)(struct nvme_dev *, void *)",
            "void (**a)(struct nvme_dev *, void *, struct nvme_completion *)",
            "void (**a)(struct nvme_dev *, void *, int (*)(void))"
        ]

    @_parser_test
    def test_function_pointer_args(self):
        return [
            "int _prf(int (*func)())",
            "static int func(int, void (*)(void))",
            "static int (*func)(int, void (*)(void))",
            "static int (*func [])(int, void (*)(void))",
            "int ** a(int **(*(*arg))(void))",
            "int func(int, void (*)(void))",
            "int func(void (*)(void), int)",
            "int func(int, int (*)(int))",
            "int func(int, void (*)(void *))",
            "int func(int *, void (*)(void))",
            "int func(int, int (*)(int))",
            "int func(int *, int (*)(int, int))",
            "int func(int *, int (*)(int, int), ...)",
            "int func(int (*)(int))",
            "int func(int (*)(int *), ...)",
            "int func(int (*)(int, ...))",
            "int func(int (*)(int, ...), ...)",
            "int (*a)(int (*)(int, ...), ...)"
        ]

    @_parser_test
    def test_mess_declarations(self):
        return [
            'void (*((*a)(int, ...)) []) (void) []'
        ]

    @_parser_test
    def test_extetions(self):
        return [
            '%usb.driver%',
            '$ my_function($, %usb.driver%, int)',
            '%usb.driver% function(int, void *)',
            '%usb.driver% function(int, $, %usb.driver%)'
        ]
