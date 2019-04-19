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

#include <linux/module.h>
#include <linux/pci.h>
#include <linux/usb.h>
#include <verifier/common.h>

static int ldv_pci_probe(struct pci_dev *pdev, const struct pci_device_id *id)
{
	struct usb_driver driver;

	ldv_assume(usb_register(&driver));

	return 0;
}

static struct pci_driver ldv_pci_driver = {
	.probe = ldv_pci_probe
};

static int __init ldv_init(void)
{
	ldv_assume(!pci_register_driver(&ldv_pci_driver));
	pci_unregister_driver(&ldv_pci_driver);

	return 0;
}

module_init(ldv_init);
