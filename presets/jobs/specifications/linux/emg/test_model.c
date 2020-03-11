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

#include <verifier/common.h>

int registered;
int probed;
int supress;

void ldv_initialize(void)
{
	/* NOTE Initializing EMG test states. */
	int registered = 0;
	int probed = 0;
}

void ldv_invoke_test(void)
{
	/* NOTE This test is intended to only the fact that callbacks are called. Supress rest warnings. */
	int supress = 1;
}

void ldv_invoke_callback(void)
{
	/* ASSERT Callback cannot be called without registration or after deregistration. */
	ldv_assert(registered);

	/* ASSERT Need probing before calling this callback. */
	ldv_assert(!probed);
}

void ldv_invoke_middle_callback(void)
{
	/* ASSERT Callback cannot be called without registration or after deregistration. */
	ldv_assert(registered);

	/* ASSERT Need probing before calling this callback. */
	ldv_assert(probed);
}

void ldv_invoke_reached(void) {
	/* ASSERT Test successfully passes as the callback call is reached. */
	ldv_assert(0);
}

void ldv_deregister(void)
{
	/* NOTE Deregistration has happend. */
	registered = 0;
}

void ldv_register(void)
{
	/* NOTE Registration has happend. */
	registered = 1;
}

void ldv_probe_up(void)
{
	/* NOTE Probing resources. */
	probed++;
}

void ldv_release_down(void)
{
	if (probed > 0)
		/* NOTE Releasing lately probed resources. */
		probed--;
	else
		/* ASSERT Cannot free unprobed or already released resources. */
		ldv_assert(0);
}

void ldv_release_completely(void)
{
	if (!probed)
		/* ASSERT Cannot free unprobed or already released resources. */
		ldv_assert(0);
	else
		/* NOTE Release all resources. */
		probed = 0;
}

void ldv_check_final_state(void)
{
	/* ASSERT At the end of the test all resources should be released. */
	ldv_assert(probed == 0 || supress);
	/* ASSERT At the end of the test all callbacks should be deregistered. */
	ldv_assert(registered == 0 || supress);
}
