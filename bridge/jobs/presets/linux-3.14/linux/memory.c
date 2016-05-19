#include <verifier/rcv.h>
#include <linux/device.h>
#include <linux/kernel.h>
#include <linux/types.h>

struct device_private;
/* LDV_COMMENT_CHANGE_STATE At the beginning nothing is allocated. */
int ldv_alloc_count = 0;

/* LDV_COMMENT_CHANGE_STATE Saved release function pointer. */
void (*gadget_release_pointer)(struct device *_dev);

void* __VERIFIER_alloc(size_t size);

/* LDV_COMMENT_CHANGE_STATE At the beginning nothing is allocated. */
//void* ldv_saved_drv_data;


/* MODEL_FUNC_DEF Allocate a "memory". */
void ldv_check_and_increase(void *res)
{
  ldv_assume(res <= LDV_PTR_MAX);
  if (res != 0) {
    /* CHANGE_STATE One more "memory" is allocated. */
    ldv_alloc_count++;
  }
}

/* MODEL_FUNC_DEF Allocate a "memory". */
void* ldv_alloc(size_t size)
{
  void *res = __VERIFIER_alloc(size);
  ldv_check_and_increase(res);
  /* RETURN memory */
  return res;
}

/* MODEL_FUNC_DEF Allocate zero "memory". */
void* ldv_zero_alloc(size_t size)
{
  void *res = ldv_zalloc(size);
  ldv_check_and_increase(res);
  /* RETURN memory */
  return res;
}

/* MODEL_FUNC_DEF Allocate a non zero "memory", but can return PTR_ERR. */
void* ldv_nonzero_alloc(size_t size)
{
  //functions, like memdup_user returns either valid pointer, or ptr_err
  void *res = __VERIFIER_alloc(size);
  ldv_assume(res != 0);
  if (res <= LDV_PTR_MAX) {
    /* CHANGE_STATE One more "memory" is allocated. */
    ldv_alloc_count++;
  }
  /* RETURN memory */
  return res;
}

/* MODEL_FUNC_DEF Allocate a "memory". */
void* ldv_alloc_without_counter(size_t size)
{
  void *res = __VERIFIER_alloc(size);
  ldv_assume(res <= LDV_PTR_MAX);
  /* RETURN memory */
  return res;
}

/* MODEL_FUNC_DEF Allocate a "memory". */
void* ldv_zalloc_without_counter(size_t size)
{
  void *res = ldv_zalloc(size);
  ldv_assume(res <= LDV_PTR_MAX);
  /* RETURN memory */
  return res;
}

/* MODEL_FUNC_DEF Free a "memory". */
void ldv_memory_free(void)
{
  /* CHANGE_STATE Free a "memory". */
  ldv_alloc_count--;
  //ldv_saved_drv_data = 0;
}

/* MODEL_FUNC_DEF Free a "memory". */
void ldv_condition_free()
{
  if (ldv_alloc_count > 0)
  {
    ldv_memory_free();
  }
}

/* MODEL_FUNC_DEF Free a "memory". */
void ldv_save_gadget_release(void (*func)(struct device *_dev))
{
  gadget_release_pointer = func;
}

int ldv_dev_set_drvdata(struct device *dev, void *data)
{
  dev->p = data;
  return 0;
}

void *ldv_dev_get_drvdata(const struct device *dev)
{
  return dev->p;
}

/* MODEL_FUNC_DEF All allocated memory should be freed at the end. */
void ldv_check_final_state(void)
{
  /* ASSERT Nothing should be allocated at the end. */
  ldv_assert("linux:memory:more initial at exit", ldv_alloc_count == 0);
}