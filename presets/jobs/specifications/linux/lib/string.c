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

#include <linux/types.h>
#include <ldv/linux/string.h>

size_t ldv_strlen(const char *s)
{
	unsigned int len = 0;

	for (; *s != '\0'; s++)
		len++;

	return len;
}

int ldv_strcmp(const char *cs, const char *ct)
{
	for (; *cs && *ct; cs++, ct++)
		if (*cs != *ct)
			break;

	return *cs - *ct;
}

int ldv_strncmp(const char *cs, const char *ct, __kernel_size_t count)
{
	if (!count)
		return 0;

	for (; *cs && *ct; cs++, ct++) {
		if (*cs != *ct)
			break;

		count--;

		if (!count)
			break;
	}

	return *cs - *ct;
}

int ldv_memcmp(const void *cs, const void *ct, size_t count)
{
	const unsigned char *su1, *su2;
	int res = 0;

	for (su1 = cs, su2 = ct; 0 < count; ++su1, ++su2, count--)
		if ((res = *su1 - *su2) != 0)
			break;

	return res;
}

char *ldv_strstr(const char *cs, const char *ct)
{
	size_t cs_len, ct_len;

	cs_len = ldv_strlen(cs);
	ct_len = ldv_strlen(ct);

	while (cs_len >= ct_len) {
		if (!ldv_memcmp(cs, ct, ct_len))
			return (char *)cs;

		cs_len--;
		cs++;
	}

	return NULL;
}
