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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <verifier/common.h>
#include <verifier/memory.h>
#include <verifier/nondet.h>

char *ldv_strdup(const char *s);
void ldv_exit(void);

void ldv_exit(void)
{
    ldv_assume(0);
}

char *ldv_strdup(const char *s)
{
    char *new;
    if (ldv_undef_int()) {
        new = ldv_xmalloc(sizeof(char));
        memcpy(new, s, sizeof(char));
        return new;
    } else {
        return 0;
    }
}