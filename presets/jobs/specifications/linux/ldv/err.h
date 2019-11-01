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

#ifndef __LINUX_LDV_ERR_H
#define __LINUX_LDV_ERR_H

/* Pointers greater then this number correspond to errors. We can't use
 * original value defined in linux/err.h ((unsigned long)-4095) since it is
 * too hard for verifiers.
 */
#define LDV_PTR_MAX ((unsigned int)-1)

long ldv_is_err(const void *ptr);
long ldv_is_err_or_null(const void *ptr);
void *ldv_err_ptr(long error);
long ldv_ptr_err(const void *ptr);

#endif /* __LINUX_LDV_ERR_H */
