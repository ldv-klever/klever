# Preparing OpenStack Deployment Testing

Prior to run tests for OpenStack deployment (_test_openstack.py_) for the first time, you need to create two instances
that should persist forever:
* _klever-pytest-development_ (the _production_ mode)
* _klever-pytest-production_ (the _development_ mode)

Both instances should have 2 VCPUs (corresponding to 8 GB of memory) and 50 GB of disk space.
They will be used to test update facilities for which it is necessary to have formerly deployed Klever instances.
