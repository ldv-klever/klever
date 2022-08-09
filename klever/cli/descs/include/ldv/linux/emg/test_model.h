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

void ldv_initialize(void);
void ldv_invoke_callback(void);
void ldv_invoke_test(void);
void ldv_invoke_middle_callback(void);
void ldv_invoke_reached(void);
void ldv_deregister(void);
void ldv_register(void);
void ldv_probe_up(void);
void ldv_release_down(void);
void ldv_release_completely(void);
void ldv_check_final_state(void);
void ldv_store_resource1(void *resource);
void ldv_store_resource2(void *resource);
void ldv_store_resource3(void *resource);
void ldv_check_resource1(void *resource);
void ldv_check_resource2(void *resource);
void ldv_check_resource3(void *resource);
void ldv_store_irq(int irq);
void ldv_check_irq(int irq);
