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

#ifndef __LDV_USERSPACE_COMMON_H
#define __LDV_USERSPACE_COMMON_H

#include <ldv/common/model.h>

/**
 * ldv_filter_err_code() - filter positive return values after a call of module callbacks.
 * @ret_val:	           Return value of module callback.
 *
 * ldv_filter_err_code() is very like ldv_post_init().
 */
extern int ldv_filter_err_code(int ret_val);

#endif /* __LDV_USERSPACE_COMMON_H */
