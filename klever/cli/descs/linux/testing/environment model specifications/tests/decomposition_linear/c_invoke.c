/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

/* TODO: it would be better to consider this as a C program rather than a Linux kernel loadable module since there is no
         any corresponding specifics. */

#include <linux/module.h>
#include <ldv/linux/emg/test_model.h>

void a(int param)
{
    return;
}

void b(int param)
{
    return;
}

void c(int param)
{
    if (param == 1)
        ldv_invoke_reached();
}

MODULE_LICENSE("GPL");
