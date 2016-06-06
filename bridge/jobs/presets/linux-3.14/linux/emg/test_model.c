int registered = 0;
int non_deregistered = 0;
int probed = 0;

/* Check that callback can be called*/
void ldv_invoke_callback(void)
{
    /* Callback cannot be called outside registration and deregistration functions*/
    ldv_assert(!non_deregistered && registered);

    /* Check that resources are allocated and freed */
    ldv_assert(!probed);
}

/* Check that callback which requires allocated resources can be called */
void ldv_invoke_middle_callback(void)
{
    /* Callback cannot be called outside registration and deregistration functions*/
    ldv_assert(!non_deregistered && registered);

    /* Check that resources are allocated and freed */
    ldv_assert(probed);
}

/* If function can be reached then produce an unsafe verdict to guarantee that there is a trace to the callback */
void ldv_invoke_reached(void) {
    ldv_assert(0);
}

/* Call if callbacks registration function has been successfully called */
void ldv_deregister(void)
{
    non_deregistered = 1;
}

/* Call if callbacks deregistration function has been successfully called*/
void ldv_register(void)
{
    registered = 1;
}

/* More resources are allocated */
void ldv_probe_up(void)
{
    probed++;
}

/* More resources are freed */
void ldv_release_down(void)
{
    probed--;
}

