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

.. note:: Althouth we would like to support different `OpenStack <https://www.openstack.org/>`__ environments, we
          tested :ref:`openstack_deploy` just for the `ISP RAS one <http://www.bigdataopenlab.ru/about.html>`__.

Additional Software Requirements
--------------------------------

To install additional packages required only by OpenStack deployment scripts you need to execute the following command::

    $ pip install ".[openstack]"

.. note:: If in the previous step you installed Klever package with the `-e` argument, then you should use it here as
          well (i.e. execute `pip install -e ".[openstack]"`).

Supported Options
-----------------

:ref:`openstack_deploy` supports 2 kinds of entities:

* :ref:`klever_base_image` - with default settings this is a Debian 9 OpenStack image with installed Klever
  dependencies.
  Using :ref:`klever_base_image` allows to substantially reduce a time for deploying other entities.
* :ref:`klever_inst` - an OpenStack instance, either for development or production purposes.
  For development mode many debug options are activated by default.

Almost all deployment commands require you to specify path to the private SSH key and your OpenStack username:

.. parsed-literal::

    $ klever-deploy-openstack --os-username :term:`$OS_USERNAME` --ssh-rsa-private-key-file :term:`$SSH_RSA_PRIVATE_KEY_FILE` create instance

For brevity they are omitted from the following examples.

Also, in addition to command-line arguments mentioned above and below, there are several optional command-line arguments which you can
find out by running:

.. code-block:: bash

   $ klever-deploy-openstack --help

.. _klever_base_image:

Klever Base Image
-----------------

For :ref:`klever_base_image` you can execute actions *show*, *create* and *remove*.
The common workflow for :ref:`klever_base_image` is :menuselection:`create --> remove`, e.g.:

.. code-block:: bash

    $ klever-deploy-openstack create image

Unless specified, name *Klever Base v2* is used for new :ref:`klever_base_image`.
If there is already an image with such name you will need to either remove it (using remove action),
or to use a new name for the image. New images can be incompatible with older deployment scripts, so it is better
to use a new name for the image if there are some drastic changes inside:

.. code-block:: bash

    $ klever-deploy-openstack --name "Klever Base v3" create image

.. _klever_inst:

Klever Instance
---------------

For :ref:`klever_inst` you can execute actions *show*, *create*, *update*, *ssh*, *remove*, *share* and *hide*.
Basically you should perform actions with :ref:`klever_inst` in the following order:
:menuselection:`create --> update --> update --> ... --> update --> remove` exactly as for :ref:`local_deploy`, e.g.:

.. parsed-literal::

    $ klever-deploy-openstack create instance

By default Klever is deployed in production mode, but you can change this with *--mode* argument. In development mode many debug options are activated by default:

.. parsed-literal::

    $ klever-deploy-openstack --mode development create instance

In addition, between creating and removing you can also *share*/*hide* for/from the outside world :ref:`klever_inst`
and open an SSH connection to it.
By default name for :ref:`klever_inst` is a concatenation of :term:`$OS_USERNAME`, "klever", and mode used (development or production).
Example: *petrov-klever-development*.

.. _klever_insts:

Multiple Klever Instances
-------------------------

You can also create a specified number of OpenStack instances for performing various experiments.
In this mode you can only execute actions *show*, *create*, *update* and *remove*.
The normal workflow for :ref:`klever_insts` is the same as for :ref:`klever_inst`, e.g.:

.. parsed-literal::

    $ klever-deploy-openstack --instances :term:`$INSTANCES` create instance
