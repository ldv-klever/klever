#include <kernel.h>
#include <ldv/verifier/memory.h>

struct resource *ldv_allocate_resource(int init)
{
    struct resource *r;

    if (init % 2)
        return NULL;

    r = ldv_xmalloc(sizeof(*r));
    r->x = init;

    return r;
}

void ldv_release_resource(struct resource *r)
{
    ldv_free(r);
}
