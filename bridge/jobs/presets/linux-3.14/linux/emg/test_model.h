/* Check that callback can be called */
void ldv_invoke_callback(void);

/* Check that callback which requires allocated resources can be called */
void ldv_invoke_middle_callback(void);

/* If function can be reached then produce an unsafe verdict to guarantee that there is a trace to the callback */
void ldv_invoke_reached(void);

/* Call if callbacks registration function has been successfully called */
void ldv_deregister(void);

/* Call if callbacks deregistration function has been successfully called */
void ldv_register(void);

/* More resources are allocated */
void ldv_probe_up(void);

/* More resources are freed */
void ldv_release_down(void);

/* Free all resources */
void ldv_release_completely(void);
