/*
 * Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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

#define LDV_STR     "LDV string"
#define LDV_STR_LEN 10

static int __init ldv_init(void)
{
	const char *s = LDV_STR;

	if (strlen(LDV_STR) != LDV_STR_LEN)
		ldv_unexpected_memory_safety_error();

	if (strlen(s) != LDV_STR_LEN)
		ldv_unexpected_memory_safety_error();

	if (strcmp(s, LDV_STR))
		ldv_unexpected_memory_safety_error();

    if (strcmp(s, "LDV substring") > 0)
		ldv_unexpected_memory_safety_error();

    if (strcmp(s, "LDV") < 0)
		ldv_unexpected_memory_safety_error();

	if (strncmp(s, LDV_STR, LDV_STR_LEN))
		ldv_unexpected_memory_safety_error();

    if (strncmp(s, "LDV substring", 5))
		ldv_unexpected_memory_safety_error();

    if (strncmp(s, "LDV substring", 6) > 0)
		ldv_unexpected_memory_safety_error();

    if (strncmp(s, "LDV substring", 7) > 0)
		ldv_unexpected_memory_safety_error();

    if (strncmp(s, "LDV", LDV_STR_LEN) < 0)
		ldv_unexpected_memory_safety_error();

    if (strcmp(strstr(s, "str"), "string"))
		ldv_unexpected_memory_safety_error();

    if (strstr(s, "Klever"))
		ldv_unexpected_memory_safety_error();

	return 0;
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
