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

/* MODEL_FUNC Initialize EMG test requirement. */
void ldv_initialize(void)
{
	/* NOTE Initializing EMG test states. */
	int registered = 0;
	int probed = 0;
}

/* MODEL_FUNC Supress unrelevant warnings. */
void ldv_invoke_test(void)
{
	/* NOTE This test is intended to only the fact that callbacks are called. Supress rest warnings. */
	int supress = 1;
}

/* MODEL_FUNC Callback reached. */
void ldv_invoke_callback(void)
{
	/* ASSERT Callback cannot be called without registration or after deregistration. */
	ldv_assert(registered);

	/* ASSERT Need probing before calling this callback. */
	ldv_assert(!probed);
}

/* MODEL_FUNC Middle callback reached. */
void ldv_invoke_middle_callback(void)
{
	/* ASSERT Callback cannot be called without registration or after deregistration. */
	ldv_assert(registered);

	/* ASSERT Need probing before calling this callback. */
	ldv_assert(probed);
}

/* MODEL_FUNC Callback has been called successfully, the test should pass. */
void ldv_invoke_reached(void) {
	/* ASSERT Test successfully passes as the callback call is reached. */
	ldv_assert(0);
}

/* MODEL_FUNC Deregistration is done. */
void ldv_deregister(void)
{
	/* NOTE Deregistration has happend. */
	registered = 0;
}

/* MODEL_FUNC Registration is done. */
void ldv_register(void)
{
	/* NOTE Registration has happend. */
	registered = 1;
}

/* MODEL_FUNC Called probing callback. */
void ldv_probe_up(void)
{
	/* NOTE Probing resources. */
	probed++;
}

/* MODEL_FUNC Called releasing callback. */
void ldv_release_down(void)
{
	if (probed > 0)
		/* NOTE Releasing lately probed resources. */
		probed--;
	else
		/* ASSERT Cannot free unprobed or already released resources. */
		ldv_assert(0);
}

/* MODEL_FUNC All resources are released. */
void ldv_release_completely(void)
{
	if (!probed)
		/* ASSERT Cannot free unprobed or already released resources. */
		ldv_assert(0);
	else
		/* NOTE Release all resources. */
		probed = 0;
}

/* MODEL_FUNC Check that all sysfs groups are not incremented at the end */
void ldv_check_final_state(void)
{
	/* ASSERT At the end of the test all resources should be released. */
	ldv_assert(probed == 0 || supress);
	/* ASSERT At the end of the test all callbacks should be deregistered. */
	ldv_assert(registered == 0 || supress);
}
