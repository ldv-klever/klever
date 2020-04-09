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
#include <linux/clk.h>
#include <ldv/verifier/nondet.h>

static int __init ldv_init(void)
{
	struct device *dev1 = ldv_undef_ptr(), *dev2 = ldv_undef_ptr();
	const char *id1 = ldv_undef_ptr(), *id2 = ldv_undef_ptr();
	struct clk *clk1, *clk2;

	clk1 = clk_get(dev1, id1);
	clk2 = devm_clk_get(dev2, id2);

	if (!IS_ERR(clk1))
	{
		if (!clk_enable(clk1))
			clk_disable(clk1);

		if (!clk_prepare(clk1))
			clk_unprepare(clk1);

		if (!clk_prepare_enable(clk1))
			clk_disable_unprepare(clk1);
	}

	if (!IS_ERR(clk2))
	{
		if (!clk_enable(clk2))
			clk_disable(clk2);

		if (!clk_prepare(clk2))
			clk_unprepare(clk2);

		if (!clk_prepare_enable(clk2))
			clk_disable_unprepare(clk2);
	}

	if (!IS_ERR(clk1) && !IS_ERR(clk2))
		if (!clk_enable(clk1)) {
			if (!clk_enable(clk2))
				clk_disable(clk2);

			clk_disable(clk1);
		}

	if (!IS_ERR(clk1))
		clk_put(clk1);

	if (!IS_ERR(clk2))
		clk_put(clk2);

	return 0;
}

module_init(ldv_init);
