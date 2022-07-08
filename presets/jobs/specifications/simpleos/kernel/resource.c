#include <kernel.h>
#include <ldv/common/model.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/memory.h>

/* There are 2 possible states of kernel resource allocation. */
enum LDV_RESOURCE_ALLOCATION_STATE {
    LDV_NONALLOCATED = 0,   /* Kernel resource is not allocated or it was released. */
    LDV_ALLOCATED           /* Kernel resource is allocated. */
};

static enum LDV_RESOURCE_ALLOCATION_STATE ldv_kernel_resource_state = LDV_NONALLOCATED;

struct resource *ldv_allocate_resource(int init)
{
    struct resource *r;

    if (ldv_kernel_resource_state != LDV_NONALLOCATED)
        /* ASSERT Kernel resource can be allocated only once */
        ldv_assert();

    if (!init || init % 2)
        /* NOTE Could not allocate kernel resource */
        return NULL;

    r = ldv_xmalloc(sizeof(*r));
    r->x = init;

    /* NOTE Allocate kernel resource */
    ldv_kernel_resource_state = LDV_ALLOCATED;

    /* NOTE Kernel resource was successfully allocated */
    return r;
}

void ldv_release_resource(struct resource *r)
{
    if (ldv_kernel_resource_state != LDV_ALLOCATED)
        /* ASSERT Module can release only allocated kernel resource */
        ldv_assert();

    ldv_free(r);

    /* NOTE Release kernel resource */
    ldv_kernel_resource_state = LDV_NONALLOCATED;

}

void ldv_check_final_state(void)
{
    if (ldv_kernel_resource_state != LDV_NONALLOCATED)
        /* ASSERT Kernel resource should be released at the end of work */
        ldv_assert();
}
