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

unsigned long ldv_created_cnt;
struct inode *ldv_inodes[MAX_INODES];


static int ldv_inode_init_always(struct super_block *sb, struct inode *inode)
{
	inode->i_sb = sb;
	inode->i_blkbits = sb->s_blocksize_bits;
	inode->i_flags = 0;
	inode->__i_nlink = 1;
	inode->i_opflags = 0;
	inode->i_size = 0;
	inode->i_blocks = 0;
	inode->i_bytes = 0;
	inode->i_generation = 0;
	inode->i_pipe = NULL;
	inode->i_cdev = NULL;
	inode->i_rdev = 0;
	inode->dirtied_when = 0;
	inode->i_mapping = & (inode->i_data);

	return 0;
}

struct inode *ldv_alloc_inode(struct super_block *sb)
{
	struct inode *inode;

	if (sb->s_op->alloc_inode)
		inode = sb->s_op->alloc_inode(sb);
	else
		return NULL;

	if (!inode)
		return NULL;

	/* Assume it is always successful */
	ldv_inodes[ldv_created_cnt] = inode;
	ldv_created_cnt++;
	ldv_inode_init_always(sb, inode);

	return inode;
}

void ldv_inode_init_once(struct inode *inode)
{
	__VERIFIER_memsetinode, 0, sizeof(struct inode));
}

void ldv_clear_inode(struct inode *inode)
{
	inode->i_state = I_FREEING | I_CLEAR;
}

static unsigned long ldv_find_ino(unsigned long ino)
{
	int i;

	for (i = 0; i < ldv_created_cnt; i++) {
		if (ldv_inodes[i]->i_ino == ino)
			return i;
	}

	return ldv_created_cnt;
}

struct inode *ldv_iget_locked(struct super_block *sb, unsigned long ino)
{
	unsigned long cnt;
	struct inode *inode;
	cnt = ldv_find_ino(ino);

	if (ldv_inodes[cnt])
		return ldv_inodes[cnt];

	return ldv_alloc_inode(sb);
}

void ldv_iput(struct inode *inode)
{
	/* Do nothing since current models do not track inode reference counters and save pointers to inode structures to
	   the global array. */
}

struct inode *ldv_get_root_inode(void)
{
	return ldv_inodes[0];
}
