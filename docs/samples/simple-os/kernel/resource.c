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

static struct resource __r;

struct resource *allocate_resource(int init)
{
    /* Resource was already allocated. */
    if (__r.x)
        return NULL;

    /* Initial value should not be 0. */
    if (!init)
        return NULL;

    /* Always fail at allocation of resources with odd initial values. */
    if (init % 2)
        return NULL;

    /* Successfully allocate and initialize resource. */
    __r.x = init;

    return &__r;
}

void release_resource(struct resource *r)
{
    __r.x = 0;
}

int is_resource_free(void)
{
    return __r.x == 0;
}
