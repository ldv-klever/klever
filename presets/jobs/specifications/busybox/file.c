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

#include <verifier/common.h>
#include <verifier/memory.h>
#include <verifier/nondet.h>
#include <stdio.h>

extern FILE *stdin;
extern FILE *stdout;
extern FILE *stderr;

int ldv_tmp_file_fd1 = -1;
FILE* ldv_tmp_file1 = 0;
int ldv_tmp_file_fd2 = -1;
FILE* ldv_tmp_file2 = 0;
int ldv_tmp_file_fd3 = -1;
FILE* ldv_tmp_file3 = 0;
int ldv_tmp_file_fd4 = -1;
FILE* ldv_tmp_file4 = 0;
int ldv_tmp_file_fd5 = -1;
FILE* ldv_tmp_file5 = 0;

int ldv_fileno(FILE *stream);
FILE *ldv_fopen(void);
int ldv_open(void);
FILE *ldv_fdopen(int fd);
int ldv_close(int fd);
int ldv_fclose(FILE *fp);
void ldv_faccess(FILE *stream);
void ldv_access(int fd);
int ldv_pipe(int pipefd[2]);
void ldv_check_final_state(void);

/* MODEL_FUNC Initialize standard streams */
void ldv_initialize(void)
{
	stdin = ldv_reference_xmalloc(0);
	stdout = ldv_reference_xmalloc(0);
	stderr = ldv_reference_xmalloc(0);
}

/* MODEL_FUNC Get a file descriptor of the stream */
int ldv_fileno(FILE *stream)
{
	int ret;

	// Check if it is standard
	if (stream == stdin)
		/* NOTE STDIN stream */
		return 0;
	else if (stream == stdout)
		/* NOTE STDOUT stream */
		return 1;
	else if (stream == stderr)
		/* NOTE STDERR stream */
		return 2;

	if (stream == ldv_tmp_file1)
		/* NOTE This is the first tracked file */
		return ldv_tmp_file_fd1;
	if (stream == ldv_tmp_file2)
		/* NOTE This is the second tracked file */
		return ldv_tmp_file_fd2;
	if (stream == ldv_tmp_file3)
		/* NOTE This is the third tracked file */
		return ldv_tmp_file_fd3;
	if (stream == ldv_tmp_file4)
		/* NOTE This is the fourth tracked file */
		return ldv_tmp_file_fd4;
	if (stream == ldv_tmp_file5)
		/* NOTE This is the fifth tracked file */
		return ldv_tmp_file_fd5;

	/* ASSERT Should open a FILE stream to get its file descriptor */
	ldv_assert(1);
	return ret;
}

/* MODEL_FUNC Open a new stream */
FILE *ldv_fopen(void)
{
	if (ldv_tmp_file_fd1 == -1) {
	    ldv_tmp_file_fd1 = 3;
		ldv_tmp_file1 = ldv_reference_xmalloc(0);
		/* NOTE Successfully opened the first file */
		return ldv_tmp_file1;
	}
	if (ldv_tmp_file_fd2 == -1) {
	    ldv_tmp_file_fd2 = 4;
		ldv_tmp_file2 = ldv_reference_xmalloc(0);
		/* NOTE Successfully opened the second file */
		return ldv_tmp_file2;
	}
	if (ldv_tmp_file_fd3 == -1) {
	    ldv_tmp_file_fd3 = 5;
		ldv_tmp_file3 = ldv_reference_xmalloc(0);
		/* NOTE Successfully opened the third file */
		return ldv_tmp_file3;
	}
	if (ldv_tmp_file_fd4 == -1) {
	    ldv_tmp_file_fd4 = 6;
		ldv_tmp_file4 = ldv_reference_xmalloc(0);
		/* NOTE Successfully opened the fourth file */
		return ldv_tmp_file4;
	}
	if (ldv_tmp_file_fd5 == -1) {
	    ldv_tmp_file_fd5 = 7;
		ldv_tmp_file5 = ldv_reference_xmalloc(0);
		/* NOTE Successfully opened the fifth file */
		return ldv_tmp_file5;
	}
	if (ldv_undef_int())
	    return 0;
	else
	    ldv_assume(0);
}

/* MODEL_FUNC Open a new file */
int ldv_open(void)
{
	if (ldv_tmp_file_fd1 == -1) {
	    ldv_tmp_file_fd1 = 3;
		/* NOTE Successfully opened the first file */
		return ldv_tmp_file_fd1;
	}
	if (ldv_tmp_file_fd2 == -1) {
	    ldv_tmp_file_fd2 = 4;
		/* NOTE Successfully opened the second file */
		return ldv_tmp_file_fd2;
	}
	if (ldv_tmp_file_fd3 == -1) {
	    ldv_tmp_file_fd3 = 5;
		/* NOTE Successfully opened the third file */
		return ldv_tmp_file_fd3;
	}
	if (ldv_tmp_file_fd4 == -1) {
	    ldv_tmp_file_fd4 = 6;
		/* NOTE Successfully opened the fourth file */
		return ldv_tmp_file_fd4;
	}
	if (ldv_tmp_file_fd5 == -1) {
	    ldv_tmp_file_fd5 = 7;
		/* NOTE Successfully opened the fifth file */
		return ldv_tmp_file_fd5;
	}
	if (ldv_undef_int())
	    return ldv_undef_int_negative();
	else
	    ldv_assume(0);
}

/* MODEL_FUNC Open a stream for an opened file descriptor */
FILE *ldv_fdopen(int fd)
{
	if (fd == 0)
		/* NOTE Get the file descriptor of STDIN */
		return stdin;
	if (fd == 1)
		/* NOTE Get the file descriptor of STDOUT */
		return stdout;
	if (fd == 2)
		/* NOTE Get the file descriptor of STDEFF */
		return stdout;
	if (fd == 3) {
		/* ASSERT Should open the first file before accessing it */
		ldv_assert(ldv_tmp_file1 == 0);
		ldv_tmp_file1 = ldv_reference_xmalloc(0);
		ldv_tmp_file_fd1 = 3;
		/* NOTE Successfully opened the first file */
		return ldv_tmp_file1;
	}
	if (fd == 4) {
		/* ASSERT Should open the second file before accessing it */
		ldv_assert(ldv_tmp_file2 == 0);
		ldv_tmp_file2 = ldv_reference_xmalloc(0);
		ldv_tmp_file_fd2 = 4;
		/* NOTE Successfully opened the second file */
		return ldv_tmp_file2;
	}
	if (fd == 5) {
		/* ASSERT Successfully opened the third file before accessing it */
		ldv_assert(ldv_tmp_file3 == 0);
		ldv_tmp_file3 = ldv_reference_xmalloc(0);
		ldv_tmp_file_fd3 = 5;
		/* NOTE Successfully opened the third file */
		return ldv_tmp_file3;
	}
	if (fd == 6) {
		/* ASSERT Should open the fourth file before accessing it */
		ldv_assert(ldv_tmp_file4 == 0);
		ldv_tmp_file4 = ldv_reference_xmalloc(0);
		ldv_tmp_file_fd4 = 6;
		/* NOTE Successfully opened the fourth file */
		return ldv_tmp_file4;
	}
	if (fd == 7) {
		/* ASSERT Should open the fifth file before accessing it */
		ldv_assert(ldv_tmp_file5 == 0);
		ldv_tmp_file5 = ldv_reference_xmalloc(0);
		ldv_tmp_file_fd5 = 7;
		/* NOTE Successfully opened the fifth file */
		return ldv_tmp_file5;
	}
	if (ldv_undef_int())
	    return 0;
	else
	    /* ASSERT Cannot open a stream of an unknown file descriptor */
	    ldv_assert(0);
}

/* MODEL_FUNC Should close an opened file descriptor */
int ldv_close(int fd)
{
	if (fd == 0 || fd == 1 || fd == 2)
		/* NOTE Close a standard stream */
		return 0;
	if (fd == 3) {
		/* ASSERT Must call close to avoid memory leak */
		ldv_assert(ldv_tmp_file1 == 0);
		/* ASSERT Should open the file stream before closing it */
		ldv_assert(ldv_tmp_file_fd1 == 3);
		ldv_tmp_file_fd1 = -1;
		ldv_tmp_file1 = 0;
		/* NOTE Close the first stream */
		return 0;
	}
	if (fd == 4) {
		/* ASSERT Must call close to avoid memory leak */
		ldv_assert(ldv_tmp_file2 == 0);
		/* ASSERT Should open the file stream before closing it */
		ldv_assert(ldv_tmp_file_fd2 == 4);
		ldv_tmp_file_fd2 = -1;
		ldv_tmp_file2 = 0;
		/* NOTE Close the second stream */
		return 0;
	}
	if (fd == 5) {
		/* ASSERT Must call close to avoid memory leak */
		ldv_assert(ldv_tmp_file3 == 0);
		/* ASSERT Should open the file stream before closing it */
		ldv_assert(ldv_tmp_file_fd3 == 5);
		ldv_tmp_file_fd3 = -1;
		ldv_tmp_file3 = 0;
		/* NOTE Close the third stream */
		return 0;
	}
	if (fd == 6) {
		/* ASSERT Must call close to avoid memory leak */
		ldv_assert(ldv_tmp_file4 == 0);
		/* ASSERT Should open the file stream before closing it */
		ldv_assert(ldv_tmp_file_fd4 == 6);
		ldv_tmp_file_fd4 = -1;
		ldv_tmp_file4 = 0;
		/* NOTE Close the fourth stream */
		return 0;
	}
	if (fd == 7) {
		/* ASSERT Must call close to avoid memory leak */
		ldv_assert(ldv_tmp_file5 == 0);
		/* ASSERT Should open the file stream before closing it */
		ldv_assert(ldv_tmp_file_fd5 == 7);
		ldv_tmp_file_fd5 = -1;
		ldv_tmp_file5 = 0;
		/* NOTE Close the fifth stream */
		return 0;
	}
	/* ASSERT Should open the file stream before closing it */
	ldv_assert(0);
}

/* MODEL_FUNC Should close an opened stream or a standard stream */
int ldv_fclose(FILE *fp)
{
	if (fp == stdin || fp == stdout || fp == stderr)
		/* NOTE Close a standard stream by its descriptor */
		return 0;
	if (fp == ldv_tmp_file1) {
		/* ASSERT Should open the file before closing it */
		ldv_assert(ldv_tmp_file_fd1 == 3);
		ldv_tmp_file_fd1 = -1;
		ldv_tmp_file1 = 0;
		/* NOTE Close the first file */
		return 0;
	}
	if (fp == ldv_tmp_file2) {
		/* ASSERT Should open the file before closing it */
		ldv_assert(ldv_tmp_file_fd2 == 4);
		ldv_tmp_file_fd2 = -1;
		ldv_tmp_file2 = 0;
		/* NOTE Close the second file */
		return 0;
	}
	if (fp == ldv_tmp_file3) {
		/* ASSERT Should open the file before closing it */
		ldv_assert(ldv_tmp_file_fd3 == 5);
		ldv_tmp_file_fd3 = -1;
		ldv_tmp_file3 = 0;
		/* NOTE Close the third file */
		return 0;
	}
	if (fp == ldv_tmp_file4) {
		/* ASSERT Should open the file before closing it */
		ldv_assert(ldv_tmp_file_fd4 == 6);
		ldv_tmp_file_fd4 = -1;
		ldv_tmp_file4 = 0;
		/* NOTE Close the fourth file */
		return 0;
	}
	if (fp == ldv_tmp_file5) {
		/* ASSERT Should open the file before closing it */
		ldv_assert(ldv_tmp_file_fd5 == 7);
		ldv_tmp_file_fd5 = -1;
		ldv_tmp_file5 = 0;
		/* NOTE Close the fifth file */
		return 0;
	}
	/* ASSERT Should open the file before closing it */
	ldv_assert(0);
}

/* MODEL_FUNC Should read from an opened stream */
void ldv_faccess(FILE *fp)
{
	if (fp == stdin || fp == stdout || fp == stderr)
		/* NOTE Access a standard stream */
		return;
	if (fp == ldv_tmp_file1) {
		/* ASSERT Should open the stream before closing it */
		ldv_assert(ldv_tmp_file_fd1 == 3);
		/* NOTE Access the first stream */
		return;
	}
	if (fp == ldv_tmp_file2) {
		/* ASSERT Should open the stream before closing it */
		ldv_assert(ldv_tmp_file_fd2 == 4);
		/* NOTE Access the second stream */
		return;
	}
	if (fp == ldv_tmp_file3) {
		/* ASSERT Should open the stream before closing it */
		ldv_assert(ldv_tmp_file_fd3 == 5);
		/* NOTE Access the third stream */
		return;
	}
	if (fp == ldv_tmp_file4) {
		/* ASSERT Should open the stream before closing it */
		ldv_assert(ldv_tmp_file_fd4 == 6);
		/* NOTE Access the fourth stream */
		return;
	}
	if (fp == ldv_tmp_file5) {
		/* ASSERT Should open the stream before closing it */
		ldv_assert(ldv_tmp_file_fd5 == 7);
		/* NOTE Access the fifth stream */
		return;
	}
	/* ASSERT Should open the stream before accessing it */
	ldv_assert(0);
}

/* MODEL_FUNC Should read from an opened file descriptor */
void ldv_access(int fd)
{
	if (fd == 0 || fd == 1 || fd == 2)
		return;
	if (fd == 3) {
		/* ASSERT Should open the file before accessing it */
		ldv_assert(ldv_tmp_file_fd1 == 3);
		/* NOTE Access the first file */
		return;
	}
	if (fd == 4) {
		/* ASSERT Should open the file before accessing it */
		ldv_assert(ldv_tmp_file_fd2 == 4);
		/* NOTE Access the second file */
		return;
	}
	if (fd == 5) {
		/* ASSERT Should open the file before accessing it */
		ldv_assert(ldv_tmp_file_fd3 == 5);
		/* NOTE Access the third file */
		return;
	}
	if (fd == 6) {
		/* ASSERT Should open the file before accessing it */
		ldv_assert(ldv_tmp_file_fd4 == 6);
		/* NOTE Access the fourth file */
		return;
	}
	if (fd == 7) {
		/* ASSERT Should open the file before accessing it */
		ldv_assert(ldv_tmp_file_fd5 == 7);
		/* NOTE Access the fifth file */
		return;
	}
	/* ASSERT Cannot access an unopened file */
	ldv_assert(0);
}

/* MODEL_FUNC Should open file descriptors for a pipe */
int ldv_pipe(int pipefd[2])
{
    if (ldv_undef_int()) {
        /* NOTE Open pipe file descriptors */
        pipefd[0] = ldv_open();
        pipefd[1] = ldv_open();
        return 0;
    } else {
        /* NOTE Fail opening file descriptors */
	    return -1;
    }
}

void ldv_check_final_state(void)
{
    /* ASSERT Missed closing the first file */
	ldv_assert(ldv_tmp_file1 == 0);
	/* ASSERT Missed closing the second file */
	ldv_assert(ldv_tmp_file2 == 0);
	/* ASSERT Missed closing the third file */
	ldv_assert(ldv_tmp_file3 == 0);
	/* ASSERT Missed closing the fourth file */
	ldv_assert(ldv_tmp_file4 == 0);
	/* ASSERT Missed closing the fifth file */
	ldv_assert(ldv_tmp_file5 == 0);
}
