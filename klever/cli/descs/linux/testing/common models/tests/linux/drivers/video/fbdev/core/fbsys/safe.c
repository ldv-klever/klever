/*
 * Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

#include <linux/module.h>
#include <linux/fb.h>
#include <ldv/common/test.h>

struct ldv_par
{
	int x;
};

static int __init ldv_init(void)
{
	struct fb_info *info;
	struct device *dev = ldv_undef_ptr_non_null();

	info = framebuffer_alloc(sizeof(struct ldv_par), dev);

	if (!info)
		return ldv_undef_int_negative();

	if (*(char *)info)
		ldv_unexpected_memory_safety_error();

	if (*((char *)info + sizeof(struct fb_info) - 1))
		ldv_unexpected_memory_safety_error();

	if (info->par != (char *)info + sizeof(struct fb_info))
		ldv_unexpected_memory_safety_error();

	if (*((char *)info + sizeof(struct fb_info) + sizeof(struct ldv_par) - 1))
		ldv_unexpected_memory_safety_error();

	framebuffer_release(info);

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
