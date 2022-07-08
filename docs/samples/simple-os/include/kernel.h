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

#ifndef __KERNEL_H
#define __KERNEL_H

#define NULL (void *)0

#define ARRAY_SIZE(a) (sizeof(a) / sizeof(a[0]))

/* The only kernel resource available for modules. */
struct resource
{
    int x;
};

/* Allocate and release kernel resource. Its initial value should not be equal to 0.
   Each module can allocate the only kernel resource and it should release successfully allocated resource. */
extern struct resource *allocate_resource(int);
extern void release_resource(struct resource *);
extern int is_resource_free(void);

#endif /* __KERNEL_H */
