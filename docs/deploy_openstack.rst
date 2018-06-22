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

Althouth we would like to support different `OpenStack <https://www.openstack.org/>`__ environments, at the moment
:ref:`openstack_deploy` likely works just for the `ISP RAS one <http://www.bigdataopenlab.ru/about.html>`__.

Prior to proceding to :ref:`openstack_deploy`, it is necessary to perform :ref:`deploy_common`.
Additionally you need to install following Python3 packages:

* `cinderclient <https://pypi.python.org/pypi/python-cinderclient>`__.
* `glanceclient <https://pypi.python.org/pypi/python-glanceclient>`__.
* `keystoneauth1 <https://pypi.python.org/pypi/keystoneauth1>`__.
* `neutronclient <https://pypi.python.org/pypi/python-neutronclient>`__.
* `novaclient <https://pypi.python.org/pypi/python-novaclient/>`__.
* `paramiko <http://www.paramiko.org/>`__.
* `pycryptodome <https://www.pycryptodome.org>`__.

:ref:`openstack_deploy` supports 3 kinds of entities:

* :ref:`klever_base_image` - usually this is a Debian 9 OpenStack image with installed packages and Python3 packages
  which will most likely required for Klever.
  Using :ref:`klever_base_image` allows to substantially reduce a time for deploying other entities.
* :ref:`klever_dev_inst` - an OpenStack instance for development purposes.
  For :ref:`klever_dev_inst` many debug options are activated by default.
* :ref:`klever_experiment_inst` - a specified number of OpenStack instances for performing various experiments.

In addition to arguments mentioned below, there are several optional arguments which you can find out by running::

   $ $KLEVER_SRC/deploys/bin/deploy-openstack --help

.. _klever_base_image:

Klever Base Image
-----------------

For :ref:`klever_base_image` you can execute actions *show*, *create* and *remove*.
The normal workflow for :ref:`klever_base_image` is ":menuselection:`create --> remove`"::

    $ $KLEVER_SRC/deploys/bin/deploy-openstack --ssh-rsa-private-key-file $SSH_RSA_PRIVATE_KEY_FILE create "Klever base image"

It is not necessary to *remove* :ref:`klever_base_image` ever for allowing one to understand what images running
OpenStack instances are based on.
Unless specified, name *Klever Base* is used for new :ref:`klever_base_image`.
If there is already an image with such the name it will be renamed by adding suffix *deprecated* (indeed, this is done
recursively with using ordinal numbers of images in addition, so, no images will be lost and there will not be any
duplicates).

.. _klever_dev_inst:

Klever Developer Instance
-------------------------

For :ref:`klever_dev_inst` you can execute actions *show*, *create*, *update*, *ssh*, *remove*, *share* and *hide*.
Basically you should perform actions with :ref:`klever_dev_inst` in the following order
":menuselection:`create --> update --> update --> ... --> update --> remove`" exactly as for :ref:`local_deploy`::

    $ $KLEVER_SRC/deploys/bin/deploy-openstack --ssh-rsa-private-key-file $SSH_RSA_PRIVATE_KEY_FILE create "Klever developer instance"

In addition, between creating and removing you can also *share*/*hide* for/from the outside world :ref:`klever_dev_inst`
and open an SSH connection to it.
By default a name for :ref:`klever_dev_inst` is a concatenation of an OpenStack username and *-klever-dev*.

.. _klever_experiment_inst:

Klever Experimental Instances
-----------------------------

For :ref:`klever_experiment_inst` you can execute actions *show*, *create* and *remove*.
The normal workflow for :ref:`klever_experiment_inst` is ":menuselection:`create --> remove`"::

    $ $KLEVER_SRC/deploys/bin/deploy-openstack --ssh-rsa-private-key-file $SSH_RSA_PRIVATE_KEY_FILE --instances $INSTANCES create "Klever experimental instances"
