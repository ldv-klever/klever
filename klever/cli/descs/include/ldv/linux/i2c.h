/*
 * Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

#ifndef __LDV_LINUX_I2C_H
#define __LDV_LINUX_I2C_H

#include <linux/types.h>

struct i2c_device_id;
struct i2c_client;

extern const struct i2c_device_id *ldv_i2c_match_id(const struct i2c_device_id *id, const struct i2c_client *client);
extern s32 ldv_i2c_smbus_read_block_data(u8 *values);

#endif /* __LDV_LINUX_I2C_H */
