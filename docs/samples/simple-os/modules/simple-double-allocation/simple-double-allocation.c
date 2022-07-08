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

static struct resource *r1, *r2;

int simple_double_allocation_init(int arg)
{
    r1 = allocate_resource(arg);
    if (!r1)
        return -100;
    r1->x = arg;

    r2 = allocate_resource(arg);
    if (!r2)
    {
        release_resource(r1);
        return -101;
    }
    r2->x = arg;

    release_resource(r1);
    release_resource(r2);

    return 0;
}
