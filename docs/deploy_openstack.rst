.. Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

.. _openstack_deploy:

OpenStack Deployment
====================

.. note:: Although we would like to support different `OpenStack <https://www.openstack.org/>`__ environments, we
          tested :ref:`openstack_deploy` just for the `ISP RAS one <https://sky.ispras.ru>`__.

Additional Software Requirements
--------------------------------

To install additional packages required only by OpenStack deployment scripts you need to execute the following command:

.. code-block:: console

  $ pip install -r requirements-openstack.txt ".[openstack]"

.. note:: If in the previous step you installed Klever package with the `-e` argument, then you should use it here as
          well (i.e. execute `pip install -r requirements-openstack.txt -e ".[openstack]"`).

Supported Options
-----------------

:ref:`openstack_deploy` supports 2 kinds of entities:

* :ref:`klever_base_image` - with default settings this is a Debian 11 OpenStack image with installed Klever
  dependencies.
  Using :ref:`klever_base_image` allows to substantially reduce a time for deploying
  :ref:`Klever Instances <klever_inst>`.
* :ref:`klever_inst` - an OpenStack instance, either for development or production purposes.
  For development mode many debug options are activated by default.

Almost all deployment commands require you to specify a path to a private SSH key and your OpenStack username:

.. code-block:: console

  $ klever-deploy-openstack --os-username $OS_USERNAME --ssh-rsa-private-key-file $SSH_RSA_PRIVATE_KEY_FILE create instance

For brevity they are omitted from the following examples.

In addition to command-line arguments mentioned above and below, there are several optional command-line arguments
which you can find out by running:

.. code-block:: console

  $ klever-deploy-openstack --help

.. _klever_base_image:

Klever Base Image
-----------------

For :ref:`klever_base_image` you can execute actions *show*, *create* and *remove*.
The common workflow for :ref:`klever_base_image` is :menuselection:`create --> remove`, e.g.:

.. code-block:: console

  $ klever-deploy-openstack create image

Unless specified, name *Klever Base vN* (where *N* is 1 plus a maximum of 0 and *vi*) is used for new
:ref:`klever_base_image`.
Besides, deployment scripts overwrites file :file:`klever/deploys/conf/openstack-base-image.txt` with this name so that
new instances will be based on the new :ref:`klever_base_image`.
To force other users to switch to the new :ref:`klever_base_image` you need to commit changes of this file to the
repository.

.. _klever_inst:

Klever Instance
---------------

For :ref:`klever_inst` you can execute actions *show*, *create*, *update*, *resize*, *share*, *hide*, *ssh* and
*remove*.
Basically you should perform actions with :ref:`klever_inst` in the following order:
:menuselection:`create --> update/resize --> update/resize --> ... --> update/resize --> remove` like for
:ref:`local_deploy`, e.g.:

.. code-block:: console

  $ klever-deploy-openstack create instance

By default Klever is deployed in the production mode, but you can change this with the *\--mode* command-line argument:

.. code-block:: console

  $ klever-deploy-openstack --mode development create instance

By using *resize* you can increase/decrease occupied computational resources and, thus, either speed up the verification
process considerably or do not waste always necessary CPU cores and memory.
You should take into account that it is enough to specify only the number of required CPU cores, e.g. 1, 2, 4, etc.,
since there is a rule of thumb to compute the appropriate size of memory (4x of the number of CPU cores) while disk
space can not be modified during resizing.
In addition, between creation and removal of :ref:`klever_inst` you can also *share*/*hide* it for/from the outside
world and open an SSH connection to it.

.. note:: You should be especially careful with user credentials when sharing :ref:`klever_inst`.

By default name for created :ref:`klever_inst` is a concatenation of :term:`$OS_USERNAME`, "klever", and the mode used
(development or production), e.g. *petrov-klever-development*.

.. _klever_insts:

Multiple Klever Instances
-------------------------

You can also create a specified number of OpenStack instances for performing various experiments by using the
*\--instances* command-line argument.
In this mode you can only execute actions *show*, *create*, *update* and *remove*.
The normal workflow for :ref:`klever_insts` is the same as for :ref:`klever_inst`, e.g.:

.. code-block:: console

  $ klever-deploy-openstack --instances $INSTANCES create instance
