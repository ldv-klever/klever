#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/irq.h>
#include <linux/slab.h>
#include <linux/gfp.h>
#include <linux/skbuff.h>
#include <linux/slab.h>
#include <linux/mempool.h>
#include <linux/dmapool.h>
#include <linux/dma-mapping.h>
#include <linux/vmalloc.h>


static struct my_struct
{
	const char *name;
	unsigned int *irq;
};

static int undef_int(void)
{
	int nondet;
	return nondet;
}

static void memory_allocation_nonatomic(void)
{
	int size, node;
	void *mem;
	if (undef_int()) mem = vmalloc(size);
	if (undef_int()) mem = vzalloc(size);
	if (undef_int()) mem = vmalloc_user(size);
	if (undef_int()) mem = vmalloc_node(size, node);
	if (undef_int()) mem = vzalloc_node(size, node);
	if (undef_int()) mem = vmalloc_exec(size);
	if (undef_int()) mem = vmalloc_32(size);
	if (undef_int()) mem = vmalloc_32_user(size);
}

static irqreturn_t my_func_irq(int irq, void *dev_id)
{
	memory_allocation_nonatomic();
	return IRQ_HANDLED;
}


static int my_usb_probe(struct usb_interface *intf, const struct usb_device_id *id)
{
	struct my_struct *err;
	err->name = "struct_name";
	err = request_irq(err->irq, my_func_irq, IRQF_SHARED, err->name, err);
	return PTR_ERR(err);
}

static struct usb_driver my_usb_driver = {
	.name = "my usb irq",
	.probe = my_usb_probe,
};

static int __init my_init(void)
{
	int ret_val = usb_register(&my_usb_driver);
	return ret_val;
}

static void __exit my_exit(void)
{
	usb_deregister(&my_usb_driver);
}

module_init(my_init);
module_exit(my_exit);
