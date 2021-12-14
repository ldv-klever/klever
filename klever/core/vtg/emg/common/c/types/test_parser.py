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

from klever.core.vtg.emg.common.c.types import import_declaration


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


def test_equality():
    tests = [
        'int x',
        'int *x',
        'void x(void)',
        'void *x(void)',
        'void *x(void *)',
        'size_t x',
        'size_t *x(size_t *)'
    ]

    for test in tests:
        obj = import_declaration(test)
        # Test that it is parsed
        assert obj
        assert obj.to_string('x') == test


@parser_test
def test_var():
    return [
        'static int a;',
        'extern int a;',
        'int a',
        'int a;'
    ]


@parser_test
def test_pars():
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


@parser_test
def test_bit_fields():
    return [
        'int a:1',
        'int a:1;',
        'unsigned char disable_hub_initiated_lpm : 1'
    ]


@parser_test
def test_arrays():
    return [
        'int a[6U]'
    ]


@parser_test
def test_tricky_names():
    return [
        'int int_a'
    ]


@parser_test
def test_var_attributes():
    return [
        'int __attribute__(()) word;',
        'size_t __attribute__((__may_alias__)) word;'
    ]


@parser_test
def test_complex_types():
    return [
        'static int a',
        'static const int a',
        'static int const a'
    ]


@parser_test
def test_pointers():
    return [
        'int * a',
        'int ** a',
        'int * const a',
        'int * const * a',
        'int * const ** a',
        'int ** const ** a'
    ]


@parser_test
def test_structs():
    return [
        'struct usb a',
        'const struct usb a',
        'const struct usb * a',
        'struct usb * const a',
    ]


@parser_test
def test_nameless_structs():
    return [
        "struct {   struct file *file;   struct page *page;   struct dir_context *ctx;   long unsigned int page_index;   u64 *dir_cookie;   u64 last_cookie;   loff_t current_index;   decode_dirent_t decode;   long unsigned int timestamp;   long unsigned int gencount;   unsigned int cache_entry_index;   unsigned char plus : 1;   unsigned char eof : 1; } nfs_readdir_descriptor_t",
        "struct { short unsigned int size; short unsigned int byte_cnt; short unsigned int threshold; } SR9800_BULKIN_SIZE[8U]"
    ]


@parser_test
def test_unions():
    return [
        'union usb * const a',
        'union {   struct sockaddr *restrict sockaddr;   } __SOCKADDR_ARG',
        'union {   s64 lock;   struct   {     u32 read;     s32 write;   }; } name',
        'union {   struct sockaddr *restrict sockaddr; } __attribute__((transparent_union)) __SOCKADDR_ARG',
        'union {   struct sockaddr *restrict sockaddr;   } __attribute__((transparent_union)) __SOCKADDR_ARG',
        'union {   struct sockaddr *restrict sockaddr;   struct sockaddr_at *restrict sockaddr_at;   struct sockaddr_ax25 *restrict sockaddr_ax25;   struct sockaddr_dl *restrict sockaddr_dl;   struct sockaddr_eon *restrict sockaddr_eon;   struct sockaddr_in *restrict sockaddr_in;   struct sockaddr_in6 *restrict sockaddr_in6;   struct sockaddr_inarp *restrict sockaddr_inarp;   struct sockaddr_ipx *restrict sockaddr_ipx;   struct sockaddr_iso *restrict sockaddr_iso;   struct sockaddr_ns *restrict sockaddr_ns;   struct sockaddr_un *restrict sockaddr_un;   struct sockaddr_x25 *restrict sockaddr_x25; } __attribute__ ((transparent_union)) __SOCKADDR_ARG;'
    ]


@parser_test
def test_nameless_unions():
    return [
        'union {   void *arg;   struct kparam_string const *str;   struct kparam_array const *arr; }',
        'union {   s64 lock;    }',
        'union {   s64 lock;   struct   {     u32 read;     s32 write;   }; }'
    ]


@parser_test
def test_typedefs():
    return [
        'mytypedef * a'
    ]


@parser_test
def test_matrix():
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


@parser_test
def test_functions():
    return [
        'int a(int)',
        'int a(int, int)',
        'int a(void)',
        'void a(void)',
        'void a(int, ...)',
        'int func(struct nvme_dev *, void *)',
        'void func(struct nvme_dev *, void *, struct nvme_completion *)'
    ]


@parser_test
def test_function_pointers():
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


@parser_test
def test_function_pointer_args():
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


@parser_test
def test_struct_attributes():
    return [
        "struct A {int x; int y;};",
        "struct A {int x; int y;} __attribute__(());",
        "struct A {int x; int y;} __attribute__((__packed__));",
        "struct B {int x; int y;} __attribute__((__aligned__));",
        "struct C {int x; int y;} __attribute__((__aligned__(b)));",
        "struct C {int x; int y;} __attribute__((__aligned__(4)));",
        "struct D {int x; int y;} __attribute__((__packed__)) __attribute__((__aligned__(4)));",
        "struct D {int x; int y;} __attribute__((__packed__)) __attribute__((format(printf, 2, 3)));",
        'struct D {int x; int y;} __attribute__((__packed__)) __attribute__((weak, alias("__f")));'
    ]


@parser_test
def test_mess_declarations():
    return [
        'void (*((*a)(int, ...)) []) (void) []'
    ]
