#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>


/* CHANGE_STATE Initialize allocated coherent counter to zero. */
int ldv_coherent_state = 0;

/* MODEL_FUNC_DEF Allocates coherent memory. */
void *ldv_usb_alloc_coherent(void)
{
    /* OTHER Choose an arbitrary memory location. */
    void *arbitrary_memory = ldv_undef_ptr();
    /* OTHER If memory is not available. */
    if (!arbitrary_memory) {
        /* RETURN Failed to allocate memory. */
        return arbitrary_memory;
    }
    /* CHANGE_STATE Increase allocated counter. */
    ldv_coherent_state += 1;
    /* RETURN The memory is successfully allocated. */
    return arbitrary_memory;
}

/* MODEL_FUNC_DEF Releases coherent memory. */
void ldv_usb_free_coherent(void *addr)
{
    if (addr) {
        /* ASSERT The memory must be allocated before. */
        ldv_assert("linux:usb:coherent:less initial decrement", ldv_coherent_state >= 1);
        /* CHANGE_STATE Decrease allocated counter. */
        ldv_coherent_state -= 1;
    }
}

/* MODEL_FUNC_DEF Check that coherent memory reference counters  are not incremented at the end. */
void ldv_check_final_state(void)
{
    /* ASSERT The coherent memory must be freed at the end. */
    ldv_assert("linux:usb:coherent:more initial at exit", ldv_coherent_state == 0);
}
