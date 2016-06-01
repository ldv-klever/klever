/* Check that callback can be called*/
void ldv_invoke_callback(void);

/* Call if callbacks registration function has been successfully called */
void ldv_deregister(void);

/* Call if callbacks deregistration function has been successfully called*/
void ldv_register(void);

/* More resources are allocated */
void ldv_probe_up(void);

/* More resources are freed */
void ldv_release_down(void);
