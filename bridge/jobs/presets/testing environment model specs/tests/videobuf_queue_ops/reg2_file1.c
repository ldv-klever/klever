#include <linux/init.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/vmalloc.h>
#include <linux/device-mapper.h>
#include <linux/dma-mapping.h>
#include <media/videobuf-dma-sg.h>
#include <media/videobuf-dma-contig.h>
#include <media/v4l2-device.h>

struct videobuf_queue q;
struct device dev;
enum v4l2_buf_type type;
enum v4l2_field field;
unsigned int msize;
void *priv;
struct videobuf_buffer *buf;

struct mutex *ldv_envgen;
static int ldv_function(void);
int deg_lock;

static int buf_prepare(struct videobuf_queue *q,struct videobuf_buffer *vb, enum v4l2_field field)
{
	int err;
	err = ldv_function();
	if(err){
		return err;
	}
	mutex_lock(ldv_envgen);
	deg_lock++;
	return 0;
}

static void buf_release(struct videobuf_queue *q,struct videobuf_buffer *vb)
{
	mutex_lock(ldv_envgen);
	deg_lock--;
}

static const struct videobuf_queue_ops ldv_ops = {
	.buf_prepare	= buf_prepare,
	.buf_release	= buf_release,
};


static int __init ldv_init(void)
{
	deg_lock = 0;
	videobuf_queue_dma_contig_init(&q,&ldv_ops,&dev,NULL,type,field,msize,priv,NULL);
	return 0;
}

static void __exit ldv_exit(void)
{
	videobuf_dma_contig_free(&q,buf);
	if(deg_lock==1){
		mutex_unlock(ldv_envgen);
	}
}

module_init(ldv_init);
module_exit(ldv_exit);
