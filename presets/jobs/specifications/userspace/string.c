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

#include <stddef.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/memory.h>
#include <ldv/verifier/nondet.h>

char *ldv_strdup(const char *s);
char *ldv_strcpy(char *dest, const char *src);
char *ldv_strncpy(char *dest, const char *src, size_t n);
size_t ldv_strlen(const char *s);

char *ldv_strdup(const char *s)
{
    char *new;
    if (ldv_undef_int()) {
        new = ldv_xmalloc(sizeof(char) * ldv_strlen(s));
        __VERIFIER_memcpy(new, s, ldv_strlen(s));
        return new;
    } else {
        return 0;
    }
}

size_t ldv_strlen(const char *str) {
    const char *s;
    for (s = str; *s; ++s) {}
    return(s - str);
}

char *ldv_strncpy(char *dest, const char *src, size_t n)
{
   size_t i;

   for (i = 0; i < n && src[i] != '\0'; i++)
       dest[i] = src[i];
   for ( ; i < n; i++)
       dest[i] = '\0';

   return dest;
}


char *ldv_strcpy(char *dest, const char *src)
{
    __VERIFIER_memcpy(dest, src, ldv_strlen(src));
    return dest;
}
