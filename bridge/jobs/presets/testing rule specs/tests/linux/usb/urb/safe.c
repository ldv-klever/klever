#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/usb.h>
#include <linux/types.h>

static int __init init(void)
{
	struct urb *tmp_1;
	struct urb *tmp_2;
	int iso_packets;
	gfp_t mem_flags;

	tmp_1 = usb_alloc_urb(iso_packets, mem_flags);
	tmp_2 = usb_alloc_urb(iso_packets, mem_flags);

	usb_free_urb(tmp_1);
	usb_free_urb(tmp_2);

	return 0;
}

module_init(init);
