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

#ifndef __LDV_VERIFIER_SET_H
#define __LDV_VERIFIER_SET_H

#if defined(LDV_SETS_MODEL_FLAG)
typedef _Bool ldv_set;
# define ldv_set_init(set) (set = 0)
# define ldv_set_add(set, element) (set = 1)
# define ldv_set_remove(set, element) (set = 0)
# define ldv_set_contains(set, element) (set == 1)
# define ldv_set_is_empty(set) (set == 0)
#elif defined(LDV_SETS_MODEL_COUNTER)
typedef int ldv_set;
# define ldv_set_init(set) (set = 0)
# define ldv_set_add(set, element) (set++)
# define ldv_set_remove(set, element) (set--)
# define ldv_set_contains(set, element) (set != 0)
# define ldv_set_is_empty(set) (set == 0)
#elif defined(LDV_SETS_MODEL_NONNEGATIVE_COUNTER)
typedef unsigned int ldv_set;
# define ldv_set_init(set) (set = 0)
# define ldv_set_add(set, element) (set++)
# define ldv_set_remove(set, element) ((set == 0) ? 1 : set--)
# define ldv_set_contains(set, element) (set != 0)
# define ldv_set_is_empty(set) (set == 0)
#else
# error "Sets are likely used but sets model is not specified"
#endif

#endif /* __LDV_VERIFIER_SET_H */
