.. Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
   Ivannikov Institute for System Programming of the Russian Academy of Sciences
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

Hardware Requirements
---------------------

We recommend following hardware to run Klever:

* 64-bit CPU with 4 cores
* 16 GB of memory
* 100 GB of free disk space

Increasing specified hardware characteristics in 2-4 times can reduce total verification time very considerably.
If you are going to run Klever non-locally, hosts at which you will deploy Klever can have much less hardware
characteristics.
To generate :ref:`klever_build_bases` for large programs, such as the Linux kernel, you need 3-5 times more free disk
space.

Software Requirements
---------------------

Deployment scripts most likely operate at any quite new Linux distribution.

Deployment Variants
-------------------

There are several variants for deploying Klever:

.. toctree::
   :maxdepth: 1

   deploy_local
   deploy_openstack
