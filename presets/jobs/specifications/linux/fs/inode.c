#define MAX_INODES 3
struct inode *ldv_inodes[MAX_INODES];
unsigned long ldv_inodes_ino[MAX_INODES];
unsigned long ldv_created_cnt;

int ldv_inode_init_always(struct super_block *sb, struct inode *inode)
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
	inode->i_bdev = NULL;
	inode->i_cdev = NULL;
	inode->i_rdev = 0;
	inode->dirtied_when = 0;
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
    inode->i_ino = ldv_inodes_ino[ldv_created_cnt];
	ldv_inode_init_always(sb, inode);

	return inode;
}

unsigned long ldv_find_ino(unsigned long ino)
{
    int i;

    for (i = 0; i <= ldv_created_cnt; i++) {
        if (ldv_inodes_ino[i] == ino)
            return i;
    }
    ldv_assume(ldv_created_cnt < (MAX_INODES - 1));
    ldv_created_cnt++;
    ldv_inodes_ino[ldv_created_cnt] = ino;
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

void ldv_clear_inode(struct inode *inode)
{
	inode->i_state = I_FREEING | I_CLEAR;
}