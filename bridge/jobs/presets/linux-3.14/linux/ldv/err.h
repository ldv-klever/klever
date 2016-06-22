#ifndef __LINUX_LDV_ERR_H
#define __LINUX_LDV_ERR_H

long ldv_is_err(const void *ptr);
long ldv_is_err_or_null(const void *ptr);
void *ldv_err_ptr(long error);
long ldv_ptr_err(const void *ptr);

#endif /* __LINUX_LDV_ERR_H */
