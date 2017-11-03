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

/* MODEL_FUNC Initialize EMG test rule specification. */
void ldv_initialize(void);

/* MODEL_FUNC Callback reached. */
void ldv_invoke_callback(void);

/* MODEL_FUNC Supress unrelevant warnings. */
void ldv_invoke_test(void);

/* MODEL_FUNC Middle callback reached. */
void ldv_invoke_middle_callback(void);

/* MODEL_FUNC Callback has been called successfully, the test should pass. */
void ldv_invoke_reached(void);

/* MODEL_FUNC Deregistration is done. */
void ldv_deregister(void);

/* MODEL_FUNC Registration is done. */
void ldv_register(void);

/* MODEL_FUNC Called probing callback. */
void ldv_probe_up(void);

/* MODEL_FUNC Called releasing callback. */
void ldv_release_down(void);

/* MODEL_FUNC All resources are released. */
void ldv_release_completely(void);

/* MODEL_FUNC Check that all sysfs groups are not incremented at the end */
void ldv_check_final_state( void );