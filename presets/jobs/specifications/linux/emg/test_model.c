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

#include <ldv/verifier/common.h>

int registered;
int probed;
int suppress;

void ldv_initialize(void)
{
	/* NOTE Initializing EMG test states. */
	int registered = 0;
	int probed = 0;
}

void ldv_invoke_test(void)
{
	/* NOTE This test is intended to only the fact that callbacks are called. suppress rest warnings. */
	int suppress = 1;
}

void ldv_invoke_callback(void)
{
	if (!registered)
		/* ASSERT Callback cannot be called without registration or after deregistration. */
		ldv_assert();

	if (probed)
		/* ASSERT Need probing before calling this callback. */
		ldv_assert();
}

void ldv_invoke_middle_callback(void)
{
	if (!registered)
		/* ASSERT Callback cannot be called without registration or after deregistration. */
		ldv_assert();

	if (!probed)
		/* ASSERT Need probing before calling this callback. */
		ldv_assert();
}

void ldv_invoke_reached(void) {
	/* ASSERT Test successfully passes as the callback call is reached. */
	ldv_assert();
}

void ldv_deregister(void)
{
	/* NOTE Deregistration has happened. */
	registered = 0;
}

void ldv_register(void)
{
	/* NOTE Registration has happened. */
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
		ldv_assert();
}

void ldv_release_completely(void)
{
	if (!probed)
		/* ASSERT Cannot free unprobed or already released resources. */
		ldv_assert();
	else
		/* NOTE Release all resources. */
		probed = 0;
}

void ldv_check_final_state(void)
{
	if (probed && !suppress)
		/* ASSERT At the end of the test all resources should be released. */
		ldv_assert();

	if (registered && !suppress)
		/* ASSERT At the end of the test all callbacks should be deregistered. */
		ldv_assert();
}
