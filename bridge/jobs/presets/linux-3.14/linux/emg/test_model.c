/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

int registered = 0;
int non_deregistered = 0;
int probed = 0;

/* Check that callback can be called */
void ldv_invoke_callback(void)
{
    /* Callback cannot be called outside registration and deregistration functions*/
    ldv_assert("linux:emg:test", !non_deregistered && registered);

    /* Check that resources are allocated and freed */
    ldv_assert("linux:emg:test", !probed);
}

/* Check that callback which requires allocated resources can be called */
void ldv_invoke_middle_callback(void)
{
    /* Callback cannot be called outside registration and deregistration functions */
    ldv_assert("linux:emg:test", !non_deregistered && registered);

    /* Check that resources are allocated and freed */
    ldv_assert("linux:emg:test", probed);
}

/* If function can be reached then produce an unsafe verdict to guarantee that there is a trace to the callback */
void ldv_invoke_reached(void) {
    ldv_assert("linux:emg:test", 0);
}

/* Call if callbacks registration function has been successfully called */
void ldv_deregister(void)
{
    non_deregistered = 1;
}

/* Call if callbacks deregistration function has been successfully called*/
void ldv_register(void)
{
    registered = 1;
}

/* More resources are allocated */
void ldv_probe_up(void)
{
    probed++;
}

/* More resources are freed */
void ldv_release_down(void)
{
    if (probed > 0)
        probed--;
    else
        ldv_assert("linux:emg:test", 0);
}

/* Free all resources */
void ldv_release_completely(void)
{
    if (!probed)
        ldv_assert("linux:emg:test", 0);
    else
        probed = 0;
}
