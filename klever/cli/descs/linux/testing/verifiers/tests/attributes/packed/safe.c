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

#include <linux/module.h>
#include <ldv/common/test.h>

#define LDV_EXPECT_TYPE_SIZE(type, size) \
        if (sizeof(type) != size)        \
            ldv_unexpected_error();

struct ldv_struct0
{
	char field1;
	short field2;
	int field3;
	char field4;
};

struct ldv_struct1
{
	char field1;
	short field2;
	int field3;
	char field4;
} __attribute__((packed));

struct ldv_struct2
{
	char field1;
	short field2;
	int field3;
	char field4;
} __attribute__((packed)) __attribute__((aligned));

static int __init ldv_init(void)
{
	struct ldv_struct0 *var0;
	struct ldv_struct1 *var1;
	struct ldv_struct2 *var2;

	LDV_EXPECT_TYPE_SIZE(struct ldv_struct0, 12);
	LDV_EXPECT_TYPE_SIZE(struct ldv_struct1, 8);
	LDV_EXPECT_TYPE_SIZE(struct ldv_struct2, 16);

	var0 = ldv_xmalloc(sizeof(*var0));
	var0->field1 = 1;
	var0->field2 = 2;
	var0->field3 = 3;
	var0->field4 = 4;

	var1 = ldv_xmalloc(sizeof(*var1));
	var1->field1 = 1;
	var1->field2 = 2;
	var1->field3 = 3;
	var1->field4 = 4;

	var2 = ldv_xmalloc(sizeof(*var2));
	var2->field1 = 1;
	var2->field2 = 2;
	var2->field3 = 3;
	var2->field4 = 4;

	ldv_free(var0);
	ldv_free(var1);
	ldv_free(var2);

	return 0;
}

module_init(ldv_init);
