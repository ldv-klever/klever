#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/types.h>

static int __init init(void)
{
	void *tmp_1;
	void *tmp_2;
	struct usb_device *dev_1, *dev_2;
	size_t size;
	gfp_t mem_flags;
	dma_addr_t *dma;

	tmp_1 = usb_alloc_coherent(dev_1, size, mem_flags, dma);
	tmp_2 = usb_alloc_coherent(dev_2, size, mem_flags, dma);

	usb_free_coherent(dev_1, size, tmp_1, &dma);
	usb_free_coherent(dev_2, size, tmp_2, &dma);

	return 0;
}

module_init(init);
