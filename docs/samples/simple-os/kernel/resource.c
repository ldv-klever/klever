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
#include <stdio.h>

static struct resource __r;

struct resource *allocate_resource(int init)
{
    if (__r.x)
    {
        printf("You should not allocate kernel resource twice.\n");
        return NULL;
    }

    if (!init)
    {
        printf("Initial value for kernel resource should not be '0'.\n");
        return NULL;
    }

    if (init % 2)
    {
        printf("Allocation of kernel resource with odd initial values always fails.\n");
        return NULL;
    }

    __r.x = init;
    printf("Kernel resource was successfully allocated and initialized.\n");

    return &__r;
}

void release_resource(struct resource *r)
{
    if (!__r.x)
        printf("You should not release non-allocated kernel resource.\n");

    __r.x = 0;
    printf("Kernel resource was successfully released.\n");
}

int is_resource_free(void)
{
    return __r.x == 0;
}
