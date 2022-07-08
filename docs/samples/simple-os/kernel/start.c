/*
 * Copyright (c) 2022 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <kernel.h>
#include <modules.h>
#include <stdlib.h>
#include <stdio.h>

typedef int (*module_init)(int);

module_init module_inits[] = {
    simple_init,
    simple_double_allocation_init,
    simple_no_check_init,
    simple_no_release_init,
    complex_init
};

/* main() requires the C runtime, in particular the standard library. From the one side, it would be better to avoid
   this for the OS kernel. From the other side, it provides capabilities to pass custom arguments at runtime easily. */
int main(int argc, const char *argv[])
{
    long module_idx, module_arg;
    char *endptr;
    int module_init_exit_code;

    if (argc != 3)
    {
        printf("Please, provide module index and argument as command-line arguments.\n");
        return -1;
    }

    module_idx = strtol(argv[1], &endptr, 10);

    if (module_idx < 0 || module_idx >= ARRAY_SIZE(module_inits))
    {
        printf("Please, provide valid module index as a first command-line argument (valid module index should be between 0 and %ld).\n", ARRAY_SIZE(module_inits) - 1);
        return -2;
    }

    module_arg = strtol(argv[2], &endptr, 10);
    module_init_exit_code = module_inits[module_idx](module_arg);

    if (module_init_exit_code)
    {
        printf("Module initialization fails with '%d' error code.\n", module_init_exit_code);
        return module_init_exit_code;
    }

    if (!is_resource_free())
    {
        printf("Module allocated kernel resource, but it did not release it.\n");
        return -10;
    }
}
