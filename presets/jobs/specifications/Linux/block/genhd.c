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

#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

struct gendisk;

enum {
	/* There are 3 possible states of disk. */
	LDV_NO_DISK = 0,    /* There is no disk or disk was put. */
	LDV_ALLOCATED_DISK, /* Disk was allocated. */
	LDV_ADDED_DISK      /* Disk was added. */
};

static int ldv_disk_state = LDV_NO_DISK;

/* MODEL_FUNC Allocate gendisk. */
struct gendisk *ldv_alloc_disk(void)
{
	/* ASSERT Gendisk should not be allocated twice. */
	ldv_assert(ldv_disk_state == LDV_NO_DISK);
	/* NOTE Choose an arbitrary return value. */
	struct gendisk *res = (struct gendisk *)ldv_undef_ptr();
	/* NOTE If memory is not available. */
	if (res) {
		/* NOTE Allocate gendisk. */
		ldv_disk_state = LDV_ALLOCATED_DISK;
		/* NOTE Gendisk was successfully created. */
		return res;
	}
	/* NOTE There was an error during gendisk creation. */
	return res;
}

/* MODEL_FUNC Add gendisk. */
void ldv_add_disk(void)
{
	/* ASSERT Gendisk should be allocated . */
	ldv_assert(ldv_disk_state == LDV_ALLOCATED_DISK);
	/* NOTE Add gendisk. */
	ldv_disk_state = LDV_ADDED_DISK;
}

/* MODEL_FUNC Delete gendisk. */
void ldv_del_gendisk(void)
{
	/* ASSERT Gendisk should be allocated . */
	ldv_assert(ldv_disk_state == LDV_ADDED_DISK);
	/* NOTE Add gendisk. */
	ldv_disk_state = LDV_ALLOCATED_DISK;
}

/* MODEL_FUNC Free gendisk. */
void ldv_put_disk(struct gendisk *disk)
{
	if (disk) {
		/* ASSERT Gendisk should be allocated . */
		ldv_assert(ldv_disk_state >= LDV_ALLOCATED_DISK);
		/* NOTE Add gendisk. */
		ldv_disk_state = LDV_NO_DISK;
	}
}

/* MODEL_FUNC Check that all sysfs groups are not incremented at the end */
void ldv_check_final_state( void )
{
	/* ASSERT Sysfs groups must be freed at the end. */
	ldv_assert(ldv_disk_state == LDV_NO_DISK);
}
