void ldv_free(const void *block) {
  free(block);
}

void *ldv_malloc(size_t size) {
  if(__VERIFIER_nondet_int()) {
    return 0;
  } else {
    void *p = malloc(size);
    __VERIFIER_assume(p != 0);
    return p;
  }
}

void *ldv_zalloc(size_t size) {
  if(__VERIFIER_nondet_int()) {
    return 0;
  } else {
    void *p = calloc(1, size);
    __VERIFIER_assume(p != 0);
    return p;
  }
}

void *ldv_init_zalloc(size_t size) {
  void *p = calloc(1, size);
  __VERIFIER_assume(p != 0);
  return p;
}

void *ldvemg_undef_ptr(size_t size) {
  void *ret = 0;

  while (ret == 0) {
     ret = __VERIFIER_nondet_pointer();
  }
  return ret;
}

int ldv_thread_create(void *thread, void function(void *func), void *data) {
    if func && !thread:
        func(data);
    return 0
}

int ldv_thread_join(void *thread) {
    return
}