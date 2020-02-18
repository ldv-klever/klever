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

.. _openstack_deploy:

OpenStack Deployment
====================

.. warning:: Althouth we would like to support different `OpenStack <https://www.openstack.org/>`__ environments, we
             tested :ref:`openstack_deploy` just for the `ISP RAS one <http://www.bigdataopenlab.ru/about.html>`__.

:ref:`openstack_deploy` supports 3 kinds of entities:

* :ref:`klever_base_image` - with default settings this is a Debian 9 OpenStack image with installed Klever
  dependencies.
  Using :ref:`klever_base_image` allows to substantially reduce a time for deploying other entities.
* :ref:`klever_dev_inst` - an OpenStack instance for development purposes.
  For :ref:`klever_dev_inst` many debug options are activated by default.
* :ref:`klever_experiment_inst` - a specified number of OpenStack instances for performing various experiments.

In addition to command-line arguments mentioned below, there are several optional command-line arguments which you can
find out by running:

.. parsed-literal::

   $ klever-deploy-openstack --help

.. _klever_base_image:

Klever Base Image
-----------------

For :ref:`klever_base_image` you can execute actions *show*, *create* and *remove*.
The common workflow for :ref:`klever_base_image` is :menuselection:`create --> remove`, e.g.:

.. parsed-literal::

    $ klever-deploy-openstack --ssh-rsa-private-key-file :term:`$SSH_RSA_PRIVATE_KEY_FILE` create "Klever base image"

Unless specified, name *Klever Base* is used for new :ref:`klever_base_image`.
If there is already an image with such the name it will be renamed automatically by adding suffix *deprecated* (indeed,
this is done recursively with using ordinal numbers of images in addition, so, no images will be lost and there will be
no duplicates).

.. _klever_dev_inst:

Klever Developer Instance
-------------------------

For :ref:`klever_dev_inst` you can execute actions *show*, *create*, *update*, *ssh*, *remove*, *share* and *hide*.
Basically you should perform actions with :ref:`klever_dev_inst` in the following order
:menuselection:`create --> update --> update --> ... --> update --> remove` exactly as for :ref:`local_deploy`, e.g.:

.. parsed-literal::

    $ klever-deploy-openstack --ssh-rsa-private-key-file :term:`$SSH_RSA_PRIVATE_KEY_FILE` create "Klever developer instance"

In addition, between creating and removing you can also *share*/*hide* for/from the outside world :ref:`klever_dev_inst`
and open an SSH connection to it.
By default a name for :ref:`klever_dev_inst` is a concatenation of an OpenStack username and *-klever-dev*.

.. _klever_experiment_inst:

Klever Experimental Instances
-----------------------------

For :ref:`klever_experiment_inst` you can execute actions *show*, *create*, *update* and *remove*.
The normal workflow for :ref:`klever_experiment_inst` is the same as for :ref:`klever_dev_inst`, e.g.:

.. parsed-literal::

    $ klever-deploy-openstack --ssh-rsa-private-key-file :term:`$SSH_RSA_PRIVATE_KEY_FILE` --instances :term:`$INSTANCES` create "Klever experimental instances"
