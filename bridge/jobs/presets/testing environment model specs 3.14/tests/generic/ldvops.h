struct ldv_resource {
    int field;
};

struct ldv_driver {
	void (*handler)(struct ldv_resource *arg);
	int (*probe)(struct ldv_resource *arg);
	void (*disconnect)(struct ldv_resource *arg);
};

int ldv_driver_register(struct ldv_driver *fops);
int ldv_driver_deregister(struct ldv_driver *fops);
