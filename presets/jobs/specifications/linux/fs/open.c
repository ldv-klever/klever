/*
 * Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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

#include <ldv/linux/fs.h>
#include <ldv/verifier/nondet.h>

int ldv_vfs_open(const struct path *path, struct file *file)
{
	if (ldv_undef_int() && path && path->dentry) {
		file->f_path = *path;

		file->f_inode = path->dentry->d_inode;
		file->f_mapping = path->dentry->d_inode->i_mapping;
		file->f_mode |= FMODE_LSEEK | FMODE_PREAD | FMODE_PWRITE;

		return 0;
	} else
		return ldv_undef_int_negative();
}
