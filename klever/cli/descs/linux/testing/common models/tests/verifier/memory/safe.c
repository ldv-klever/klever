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

#include <linux/module.h>
#include <ldv/common/test.h>
#include <ldv/linux/err.h>

static int __init ldv_init(void)
{
	size_t size = ldv_undef_uint(), nmemb = ldv_undef_uint();
	void *data;

	data = ldv_malloc(size);

	if (ldv_is_err(data))
		ldv_unexpected_error();

	ldv_free(data);

	data = ldv_calloc(nmemb, size);

	if (ldv_is_err(data))
		ldv_unexpected_error();

	ldv_free(data);

	data = ldv_zalloc(size);

	if (ldv_is_err(data))
		ldv_unexpected_error();

	ldv_free(data);

	data = ldv_xmalloc(size);

	if (!data || ldv_is_err(data))
		ldv_unexpected_error();

	ldv_free(data);

	data = ldv_xzalloc(size);

	if (!data || ldv_is_err(data))
		ldv_unexpected_error();

	ldv_free(data);

	data = ldv_malloc_unknown_size();

	if (ldv_is_err(data))
		ldv_unexpected_error();

	ldv_free(data);

	data = ldv_calloc_unknown_size();

	if (ldv_is_err(data))
		ldv_unexpected_error();

	ldv_free(data);

	data = ldv_zalloc_unknown_size();

	if (ldv_is_err(data))
		ldv_unexpected_error();

	ldv_free(data);

	/*
	 * We don't test ldv_xmalloc_unknown_size() and external_allocated_data()
	 * since they are too specific.
	 */

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
