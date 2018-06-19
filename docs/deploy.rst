.. Copyright (c) 2018 ISPRAS (http://www.ispras.ru)
   Institute for System Programming of the Russian Academy of Sciences
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

Deployment
==========

Klever does not support standard deployment means because it consists of several components that may require
complicating setup, e.g. configuring and running a web service with a database access, running system services that
perform some preliminary actions with superuser rights, etc.
Also, Klever will likely always require several specific addons that can not be deployed in a normal way.
Please, be ready to spend quite much time if you follow this instruction first time.

There are several variants for deploying Klever:

.. toctree::
   :maxdepth: 1

   deploy_local
   deploy_openstack
