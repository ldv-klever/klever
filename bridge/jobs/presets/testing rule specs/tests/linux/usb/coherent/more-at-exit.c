#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/types.h>

static int __init init(void)
{
	void *tmp_1;
	struct usb_device *dev_1;
	size_t size;
	gfp_t mem_flags;
	dma_addr_t *dma;

	tmp_1 = usb_alloc_coherent(dev_1, size, mem_flags, dma);

	return 0;
}

module_init(init);
