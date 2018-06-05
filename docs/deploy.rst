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

.. note:: Klever does not support standard deployment means because of it consists of several components that may
          require complicating setup, e.g. configuring and running a web service with a database access, running system
          services partially with superuser rights, etc.
          Also, Klever will likely always require several specific addons that can not be deployed normally.

.. warning:: Do not deploy Klever at your workstation unless you are ready to lose some sensitive data or to have
             misbehaved services and programs.
             We hope that one day deployment scripts, Klever and its addons will be more safe and secure, so this
             warning will be redundant.

One can deploy Klever either :ref:`locally <local_deploy>` or within :ref:`OpenStack <openstack_deploy>`.
Most likely if you are outside ISP RAS, you need to follow the first way.

.. note:: Do not worry to make mistakes.
          Both types of deployment supports updating, so you will be able to bypass errors.
          Besides, there are specific means, e.g. uninstalling for :ref:`local_deploy` and removing
          instances for :ref:`openstack_deploy`.

.. note:: If you will encounter some unexpected issues, please, report them to us.

.. _local_deploy:

Local Deployment
----------------

At the moment local deployment scripts are intended for `Debian 9 <https://wiki.debian.org/DebianStretch>`__.
You can try to use them for other versions of Debian as well as for various
`Debian derivatives <https://wiki.debian.org/Derivatives/>`__.
For instance, they suit for `Ubuntu 18.04 <https://wiki.ubuntu.com/BionicBeaver/ReleaseNotes>`__.

Prior to proceding to :ref:`local_deploy`, it is necessary to perform :ref:`common_deploy_steps`.
Then you need to choose an appropriate mode (*development*, *production* or *testing*) and perform actions in the
following order :menuselection:`install --> update --> update --> ... --> update --> uninstall`::

    $ sudo PYTHONPATH=$KLEVER_SRC $KLEVER_SRC/deploys/bin/deploy-local --deployment-directory $KLEVER_DEPLOY_DIR --username $KLEVER_USER install production

.. note:: Do not deploy Klever twice within various deployment directories (*$KLEVER_DEPLOY_DIR*).
          Before a new installation you should uninstall the previous one if so.

In addition, there are several optional arguments which you can find out by running::

    $ sudo PYTHONPATH=$KLEVER_SRC $KLEVER_SRC/deploys/bin/deploy-local --help

.. _openstack_deploy:

OpenStack Deployment
--------------------

Althouth we would like to support different OpenStack environments, at the moment scripts likely work just for the
`ISP RAS one <http://www.bigdataopenlab.ru/about.html>`__.
Please, provide us advices if you know how to make this better.

Prior to proceding to :ref:`openstack_deploy`, it is necessary to perform :ref:`common_deploy_steps`.
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
  It allows to substantially reduce a time for deploying other entities.
* :ref:`klever_dev_inst` - an instance for development purposes.
  For it many debug options are activated by default.
* :ref:`klever_experiment_inst` - a specified number of instances for performing various experiments.

In addition to arguments mentioned below, there are several optional arguments which you can find out by running::

   $ PYTHONPATH=$KLEVER_SRC $KLEVER_SRC/deploys/bin/deploy-openstack --help

.. _klever_base_image:

Klever Base Image
^^^^^^^^^^^^^^^^^

For :ref:`klever_base_image` you can execute actions *show*, *create* and *remove*.
The normal workflow for :ref:`klever_base_image` is :menuselection:`create --> remove`::

    $ PYTHONPATH=$KLEVER_SRC $KLEVER_SRC/deploys/bin/deploy-openstack --ssh-rsa-private-key-file $SSH_RSA_PRIVATE_KEY_FILE create "Klever base image"

But actually it is not necessary to *remove* :ref:`klever_base_image` ever.
So, one will be able to understand what images running instances are based on.
Unless specified, name *Klever Base* is used for a new :ref:`klever_base_image`.
If there is already an image with such the name it will be renamed by adding suffix *deprecated* (indeed, this is done
recursively with using ordinal numbers of images in addition).

.. _klever_dev_inst:

Klever Developer Instance
^^^^^^^^^^^^^^^^^^^^^^^^^

For :ref:`klever_dev_inst` you can execute actions *show*, *create*, *update*, *ssh*, *remove*, *share* and *hide*.
Basically you should perform actions with :ref:`klever_dev_inst` in the following order
:menuselection:`create --> update --> update --> ... --> update --> remove`::

    $ PYTHONPATH=$KLEVER_SRC $KLEVER_SRC/deploys/bin/deploy-openstack --ssh-rsa-private-key-file $SSH_RSA_PRIVATE_KEY_FILE create "Klever developer instance"

In addition, between creating and removing you can also share/hide for/from the outside world :ref:`klever_dev_inst` and
open an SSH connection to it.
By default a name for :ref:`klever_dev_inst` is a concatenation of an OpenStack username and *-klever-dev*.

.. _klever_experiment_inst:

Klever Experimental Instances
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For :ref:`klever_experiment_inst` you can execute actions *show*, *create* and *remove*.
The normal workflow for :ref:`klever_experiment_inst` is :menuselection:`create --> remove`::

    $ PYTHONPATH=$KLEVER_SRC $KLEVER_SRC/deploys/bin/deploy-openstack --ssh-rsa-private-key-file $SSH_RSA_PRIVATE_KEY_FILE --instances $INSTANCES create "Klever experimental instances"

.. _common_deploy_steps:

Common Deployment Steps
-----------------------

To execute deployment script you need:

* `Python 3.4 or higher <https://www.python.org/>`_.
* `bzip2 <http://www.bzip.org/>`__, `git <https://git-scm.com/>`__, `gz <https://www.gnu.org/software/gzip/>`__,
  `tar <https://www.gnu.org/software/tar/>`__ and `xz <https://tukaani.org/xz/>`__ (if you are going to deploy Klever,
  its addons or programs to be verified from corresponding sources).

Before deployment one has to get :ref:`klever_addons` and perhaps :ref:`programs`.
Both of them should be described appropriately within :ref:`deploy_conf_file`.

.. _klever_addons:

Klever Addons
^^^^^^^^^^^^^

You can provide :ref:`klever_addons` in various forms such as files, directories, archives or Git repositories.
Deployment scripts will take care of their appropriate extracting.
The best place for :ref:`klever_addons` is directory :file:`addons` within *$KLEVER_SRC*.

.. note:: Git does not track :file:`$KLEVER_SRC/addons`.

:ref:`klever_addons` include the following:

* :ref:`cif`.
* :ref:`cil`.
* :ref:`consul`.
* One or more :ref:`verification_backends`.
* :ref:`optional_addons`.

.. _cif:

CIF
"""

One can download `CIF <https://forge.ispras.ru/projects/cif/>`__ binaries from
`here <https://forge.ispras.ru/attachments/5738/cif-d95cdf0.tar.gz>`__.
These binaries are seem to be compatible with various Linux distributions since CIF is based on
`GCC <https://gcc.gnu.org/>`__ that has few dependencies.

Besides, one can clone `CIF Git repository <https://forge.ispras.ru/projects/cif/repository>`__ and build CIF from
source.
Please, refer to corresponding instructions.

.. _cil:

CIL
"""

`CIL <https://people.eecs.berkeley.edu/~necula/cil/>`__ is a very legacy Klever addon.
You can get its binaries from `here <https://forge.ispras.ru/attachments/5739/cil-1.5.1.tar.gz>`__.
We do not recommend to build it from source since we have applied several specific patches.

.. _consul:

Consul
""""""

One can download appropriate `Consul <https://www.consul.io/>`__ binaries from
`here <http://www.consul.io/downloads.html>`__.
We are successfully using version 0.9.2 but new versions can work also.

.. _verification_backends:

Verification Backends
"""""""""""""""""""""

As a verification backend Klever supports `CPAchecker <https://cpachecker.sosy-lab.org/>`__ well.
Some other verification backends are supported experimentally and we do not recommend to use them.

You can download binaries of CPAchecker suitable for checking most of requirements from
`here <https://forge.ispras.ru/attachments/5740/CPAchecker-1.7-svn%2027946-unix.tar.gz>`__.
For finding data races additionally download binaries of another version of CPAchecker from
`here <https://forge.ispras.ru/attachments/5741/CPAchecker-1.6.1-svn%20ea117e2ecf-unix.tar.gz>`__

In addition you can clone `CPAchecker Git or Subversion repository <https://cpachecker.sosy-lab.org/download.php>`__ and
build other versions of CPAchecker from source.
Please, refer to corresponding instructions.

.. _optional_addons:

Optional Addons
"""""""""""""""

If you are going to solve verification tasks using `VerifierCloud <https://vcloud.sosy-lab.org/>`__ (you need an access
for that!), you should get an appropriate client.
Most likely one can use the client from the :ref:`CPAchecker verification backend <verification_backends>`.

.. _programs:

Programs to be Verified
^^^^^^^^^^^^^^^^^^^^^^^

Like addons one can provide programs to be verified.
At the moment this is only the `Linux kernel <https://www.kernel.org/>`__.

Providing program source code at this stage can quite considerably reduce overall verification time because of one will
not need to do that for particular verification jobs.
Sometimes, e.g. when verifying commits from Git repositories, there is not any way to set up verification jobs except
this one.
The best place for programs to be verified is directory :file:`programs` within *$KLEVER_SRC*.

.. note:: Git does not track :file:`$KLEVER_SRC/programs`.

.. _deploy_conf_file:

Deployment Configuration File
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

After preparing :ref:`klever_addons` and :ref:`programs` one needs to describe them within :ref:`deploy_conf_file`.
First we recommend to copy :file:`$KLEVER_SRC/deploys/conf/klever.json.sample` to some JSON file within
:file:`$KLEVER_SRC/deploys/conf/`, say, to :file:`$KLEVER_SRC/deploys/conf/klever.json`.
Such the :ref:`deploy_conf_file` is used by deployment scripts by default.

.. note:: Git does not track :file:`$KLEVER_SRC/deploys/conf/*.json`.
.. note:: You can prepare multiple deployment configuration files, but be careful when using them to avoid unexpected
          results due to tricky intermixes.

Then you need to describe Klever and all required :ref:`klever_addons` and :ref:`programs`.
Generally there are 3 pairs within :ref:`deploy_conf_file` with names *Klever*, *Klever Addons* and *Programs*
correspondingly.
The first one directly represents a JSON object describing Klever.
The second and the third ones are JSON objects where each pair represents a name of a particular
:ref:`Klever addon <klever_addons>` or :ref:`program to be verified <programs>` and its description as a JSON object.
There is the only exception.
Within *Klever Addons* there is *Verification Backends* that obviously serves for describing
:ref:`verification_backends`.

.. note:: Actually there may be more :ref:`klever_addons`, :ref:`verification_backends` or :ref:`programs` within
          corresponding locations.
          Deployment scripts will consider just described ones.

Each JSON object describing an entity should always have values for *version* and *path*:

* *Version* gives a very important knowledge for deployment scripts.
  Depending on values of this pair they behave appropriately.
  When entities are represented as files, directories or archives deployment scripts remember versions of
  installed/updated entities.
  So, later they update these entities just when their versions change.
  For Git repositories versions can be anything suitable for a `Git checkout <https://git-scm.com/docs/git-checkout>`__,
  e.g. appropriate Git branches, tags or commits.
  In this case deployment scripts will checkout this version first.

  .. note:: Deployment scripts clone Git repositories before checkouting, so, all uncommited changes will be ignored.

  Besides, you can specify version *CURRENT*, that enables bypassing Git checkouting.
  In this case Git repositories are treated like directories.
* *Path* sets either a path relative to :file:`$KLEVER_SRC` or an absolute path to entity (binaries, source files,
  configurations, etc.).
  As we mentioned above you can specify individual files, directories, archives and Git repositories as paths.

For some entities it could be necessary to additionally specify *executable path* within *path* if binaries are not
available directly from *path*.
For :ref:`verification_backends` there is also *name* with value *CPAchecker*.
Keep this pair for all specified :ref:`verification_backends`.
