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

#include <linux/types.h>
#include <linux/spi/spi.h>
#include <ldv/linux/device.h>
#include <ldv/verifier/memory.h>

struct spi_master *ldv_spi_alloc_master(struct device *host, unsigned size)
{
	struct spi_master *master;

	master = ldv_zalloc(size + sizeof(struct spi_master));

	if (!master)
		return NULL;

    /* In Linux ~3.14 dev_set_drvdata() is external undefined function with model ldv_dev_set_drvdata() called
       explicitly below since models are not instrumented. In Linux ~4.6 dev_set_drvdata() is static inline function
       and model has no sense while explicit call to dev_set_drvdata() will do the necessary work. */
    ldv_dev_set_drvdata(&master->dev, &master[1]);
    dev_set_drvdata(&master->dev, &master[1]);

	return master;
}

/* It is almost like ldv_spi_alloc_master() above, but it works with another structure that replaced the former one
   in new versions of the Linux kernel.
   This model is under conditions since spi_controller is not defined in old versions of the Linux kernel while we need
   to know its size. It is possible to avoid these conditions by inlining this model directly to advice body. */
#if !defined(LDV_SPECS_SET_2_6_33) && !defined(LDV_SPECS_SET_3_2) && !defined(LDV_SPECS_SET_3_14) && !defined(LDV_SPECS_SET_4_6_7)
struct spi_controller *ldv_spi_alloc_controller(struct device *host, unsigned size)
{
	struct spi_controller *controller;

	controller = ldv_zalloc(size + sizeof(struct spi_controller));

	if (!controller)
		return NULL;

    ldv_dev_set_drvdata(&controller->dev, &controller[1]);
    dev_set_drvdata(&controller->dev, &controller[1]);

	return controller;
}
#endif
