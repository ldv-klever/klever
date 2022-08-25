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

static int registered;
static int probed;
static int suppress;
static void *resource1;
static void *resource2;
static void *resource3;
static int stored_irq = -1;

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

void ldv_store_resource1(void *resource)
{
	if (resource1)
		/* ASSERT Resource 1 is already occupied. */
		ldv_assert();

	if (!resource)
		/* ASSERT Stored resource should not be NULL. */
		ldv_assert();

	resource1 = resource;
}

void ldv_store_resource2(void *resource)
{
	if (resource2)
		/* ASSERT Resource 2 is already occupied. */
		ldv_assert();

	if (!resource)
		/* ASSERT Stored resource should not be NULL. */
		ldv_assert();

	resource2 = resource;
}

void ldv_store_resource3(void *resource)
{
	if (resource3)
		/* ASSERT Resource 3 is already occupied. */
		ldv_assert();

	if (!resource)
		/* ASSERT Stored resource should not be NULL. */
		ldv_assert();

	resource3 = resource;
}

void ldv_check_resource1(void *resource, int is_free)
{
	if (!resource1)
		/* ASSERT Resource 1 was not stored yet. */
		ldv_assert();

	if (resource != resource1)
		/* ASSERT Resource 1 differs. */
		ldv_assert();

	if (is_free)
		resource1 = (void *)0;
}

void ldv_check_resource2(void *resource, int is_free)
{
	if (!resource2)
		/* ASSERT Resource 2 was not stored yet. */
		ldv_assert();

	if (resource != resource2)
		/* ASSERT Resource 2 differs. */
		ldv_assert();

	if (is_free)
		resource2 = (void *)0;
}

void ldv_check_resource3(void *resource, int is_free)
{
	if (!resource3)
		/* ASSERT Resource 3 was not stored yet. */
		ldv_assert();

	if (resource != resource2)
		/* ASSERT Resource 3 differs. */
		ldv_assert();

	if (is_free)
		resource3 = (void *)0;
}

void ldv_store_irq(int irq)
{
	if (stored_irq != -1)
		/* ASSERT IRQ is already occupied. */
		ldv_assert();

	stored_irq = irq;
}

void ldv_check_irq(int irq, int is_free)
{
	if (stored_irq == -1)
		/* ASSERT IRQ was not stored yet. */
		ldv_assert();

	if (irq != stored_irq)
		/* ASSERT IRQ differs. */
		ldv_assert();

	if (is_free)
		stored_irq = -1;
}
