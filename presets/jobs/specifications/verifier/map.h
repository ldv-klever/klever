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

#ifndef __VERIFIER_MAP_H
#define __VERIFIER_MAP_H

typedef int ldv_map;
typedef int ldv_map_value;

#define ldv_map_init(map) (map = 0)
#define ldv_map_put(map, key, value) (map = value)
#define ldv_map_get(map, key) map
#define ldv_map_contains_key(map, key) (map != 0)
#define ldv_map_remove(map, key) (map = 0)
#define ldv_map_is_empty(map) (map == 0)

#endif /* __VERIFIER_MAP_H */
