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
	short field1;
};

struct ldv_struct1
{
	short field1;
} __attribute__((aligned));

struct ldv_struct2
{
	short field1;
} __attribute__((aligned(8)));

struct ldv_struct3
{
	short field1;
} __attribute__((aligned(4)));

struct ldv_struct4
{
	short field1;
} __attribute__((aligned(2)));

struct ldv_struct5
{
	short field1;
} __attribute__((aligned(1)));

static int __init ldv_init(void)
{
	struct ldv_struct0 var0;
	struct ldv_struct1 var1;
	struct ldv_struct2 var2;
	struct ldv_struct3 var3;
	struct ldv_struct4 var4;
	struct ldv_struct5 var5;

	LDV_EXPECT_TYPE_SIZE(struct ldv_struct0, 2);
	LDV_EXPECT_TYPE_SIZE(struct ldv_struct1, 16);
	LDV_EXPECT_TYPE_SIZE(struct ldv_struct2, 8);
	LDV_EXPECT_TYPE_SIZE(struct ldv_struct3, 4);
	LDV_EXPECT_TYPE_SIZE(struct ldv_struct4, 2);
	LDV_EXPECT_TYPE_SIZE(struct ldv_struct5, 2);

	var0.field1 = 0;
	var1.field1 = 1;
	var2.field1 = 2;
	var3.field1 = 3;
	var4.field1 = 4;
	var5.field1 = 5;

	return 0;
}

module_init(ldv_init);
