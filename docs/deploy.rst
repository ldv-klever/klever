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

.. _deploy:

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

* x86-64 CPU with 4 cores
* 16 GB of memory
* 100 GB of free disk space

We do not guarantee that Klever will operate well if you will use less powerful machines.
Increasing specified hardware characteristics in 2-4 times can reduce total verification time very considerably.
To generate :ref:`klever_build_bases` for large programs, such as the Linux kernel, you need 3-5 times more free disk
space.

.. _software_requirements:

Software Requirements
---------------------

Klever deployment is designed to work on `Debian 9 <https://wiki.debian.org/DebianStretch>`__,
`Ubuntu 18.04 <https://wiki.ubuntu.com/BionicBeaver/ReleaseNotes>`__,
`Fedora 32 <https://docs.fedoraproject.org/en-US/fedora/f32/>`__ and
`openSUSE 15.2 <https://doc.opensuse.org/release-notes/x86_64/openSUSE/Leap/15.2/>`__.
You can try it for other versions of these distributions, as well as for their derivatives on your own risk.

To deploy Klever one has to clone its Git repository (a path to a directory where it is cloned is referred to as
:term:`$KLEVER_SRC`)::

    git clone --recursive https://forge.ispras.ru/git/klever.git

.. note:: Alternatively one can use https://github.com/ldv-klever/klever.git.

Then you need to install all required dependencies.

First of all it is necessary to install packages listed at the following files:

* Debian - :file:`klever/deploys/conf/debian-packages.txt` from :term:`$KLEVER_SRC`.
* Fedora - :file:`klever/deploys/conf/fedora-packages.txt` from :term:`$KLEVER_SRC`.
* openSUSE - :file:`klever/deploys/conf/opensuse-packages.txt` from :term:`$KLEVER_SRC`.

Then you need to install `Python 3.7 or higher <https://www.python.org/>`__ and a corresponding development package.
If your distribution does not have them you can get them from:

* Debian - `here <https://forge.ispras.ru/attachments/download/7251/python-3.7.6.tar.xz>`__.
* Fedora - `here <https://forge.ispras.ru/attachments/download/7252/python-fedora-3.7.6.tar.xz>`__.
* openSUSE - `here <https://forge.ispras.ru/attachments/download/9073/python-opensuse-3.7.6.tar.xz>`__.

To install required Python packages we recommend to create a virtual environment using installed Python.
For instance, you can run following commands within :term:`$KLEVER_SRC`::

    $ /usr/local/python3-klever/bin/python3 -m venv venv
    $ source venv/bin/activate

To avoid some unpleasant issues during installation we recommend to upgrade PIP and associated packages::

    $ pip install --upgrade pip wheel setuptools

.. note:: Later we assume that you are using the Klever Python virtual environment created in the way described above.

Then you need to install Python packages including the Klever one:

* For production use it is necessary to run the following command within :term:`$KLEVER_SRC`::

    $ pip install -r requirements.txt .

  Later to upgrade the Klever Python package you should run::

    $ pip install --upgrade -r requirements.txt .

* If one is going to develop Klever one should install Klever Python package in the *editable* mode (with flag *-e*).
  To do it, run the following command within :term:`$KLEVER_SRC`::

    $ pip install -r requirements.txt -e .

  In this case the Klever Python package will be updated automatically, but you may still need to upgrade its
  dependencies by running the following command::

    $ pip install --upgrade -r requirements.txt -e .


.. note:: Removing `-r requirements.txt` from the command will install latest versions of required packages.
          However, it is not guaranteed that they will work well with Klever.

Then one has to get :ref:`klever_addons` and :ref:`klever_build_bases`.
Both of them should be described appropriately within :ref:`deploy_conf_file`.

.. note:: You can omit getting :ref:`klever_addons` if you will use default :ref:`deploy_conf_file` since it contains
          URLs for all required :ref:`klever_addons`.

.. _klever_addons:

Klever Addons
-------------

You can provide :ref:`klever_addons` in various forms:

* Local files, directories, archives or Git repositories.
* Remote files, archives or Git repositories.

Deployment scripts will take care of their appropriate extracting.
If :ref:`klever_addons` are provided locally the best place for them is directory :file:`addons` within
:term:`$KLEVER_SRC` (see :ref:`klever_git_repo_struct`).

.. note:: Git does not track :file:`addons` from :term:`$KLEVER_SRC`.

:ref:`klever_addons` include the following:

* :ref:`cif`.
* :ref:`cil`.
* :ref:`consul`.
* One or more :ref:`verification_backends`.
* :ref:`optional_addons`.

.. _cif:

CIF
^^^

One can download `CIF <https://forge.ispras.ru/projects/cif/>`__ binaries from
`here <https://forge.ispras.ru/projects/cif/files>`__.
These binaries are compatible with various Linux distributions since CIF is based on `GCC <https://gcc.gnu.org/>`__
that has few dependencies.
Besides, one can clone `CIF Git repository <https://forge.ispras.ru/projects/cif/repository>`__ and build CIF from
source using corresponding instructions.

.. _cil:

Frama-C (CIL)
^^^^^^^^^^^^^

You can get `Frama-C (CIL) <https://frama-c.com/>`__ binaries from
`here <https://forge.ispras.ru/projects/klever/files>`__.
As well, you can build it from
`this source <https://forge.ispras.ru/projects/astraver/repository/framac>`__ (branch :file:`18.0`)
which has several specific patches relatively to the mainline.

.. _consul:

Consul
^^^^^^

One can download appropriate `Consul <https://www.consul.io/>`__ binaries from
`here <http://www.consul.io/downloads.html>`__.
We are successfully using version 0.9.2 but newer versions can be fine as well.
It is possible to build Consul from `source <https://github.com/hashicorp/consul>`__.

.. _verification_backends:

Verification Backends
^^^^^^^^^^^^^^^^^^^^^

You need at least one tool that will perform actual verification of your software.
These tools are referred to as :ref:`verification_backends`.
As verification backends Klever supports `CPAchecker <https://cpachecker.sosy-lab.org/>`__ well.
Some other verification backends are supported experimentally and currently we do not recommend to use them.
You can download binaries of CPAchecker from `here <https://forge.ispras.ru/projects/klever/files>`__.
In addition, you can clone `CPAchecker Git or Subversion repository <https://cpachecker.sosy-lab.org/download.php>`__
and build other versions of CPAchecker from source referring corresponding instructions.

.. _optional_addons:

Optional Addons
^^^^^^^^^^^^^^^

If you are going to solve verification tasks using `VerifierCloud <https://vcloud.sosy-lab.org/>`__, you should get an
appropriate client.
Most likely one can use the client from the :ref:`CPAchecker verification backend <verification_backends>`.

.. note:: For using VerifierCloud you need appropriate credentials.
          But anyway it is an optional addon, one is able to use Klever without it.

.. _klever_build_bases:

Klever Build Bases
------------------

In addition to :ref:`klever_addons` one should provide :ref:`klever_build_bases` obtained for software to be verified.
:ref:`klever_build_bases` should be obtained using `Clade <https://forge.ispras.ru/projects/clade>`__.
All :ref:`klever_build_bases` should be provided as directories, archives or links to remote archives.
The best place for :ref:`klever_build_bases` is the directory :file:`build bases` within :term:`$KLEVER_SRC` (see
:ref:`klever_git_repo_struct`).

.. note:: Git does not track :file:`build bases` from :term:`$KLEVER_SRC`.

.. note:: Content of :ref:`klever_build_bases` is not modified during verification.

.. _deploy_conf_file:

Deployment Configuration File
-----------------------------

After getting :ref:`klever_addons` and :ref:`klever_build_bases` one needs to describe them within
:ref:`deploy_conf_file`.
By default deployment scripts use :file:`klever/deploys/conf/klever.json` from :term:`$KLEVER_SRC`.
We recommend to copy this file somewhere and adjust it appropriately.

There are 2 pairs within :ref:`deploy_conf_file` with names *Klever Addons* and *Klever Build Bases*.
The first one is a JSON object where each pair represents a name of a particular :ref:`Klever addon <klever_addons>`
and its description as a JSON object.
There is the only exception.
Within *Klever Addons* there is *Verification Backends* that serves for describing :ref:`verification_backends`.

Each JSON object that describes a :ref:`Klever addon <klever_addons>` should always have values for *version* and
*path*:

* *Version* gives a very important knowledge for deployment scripts.
  Depending on values of this pair they behave appropriately.
  When entities are represented as files, directories or archives deployment scripts remember versions of
  installed/updated entities.
  So, later they update these entities just when their versions change.
  For Git repositories versions can be anything suitable for a `Git checkout <https://git-scm.com/docs/git-checkout>`__,
  e.g. appropriate Git branches, tags or commits.
  In this case deployment scripts checkout specified versions first.
  Also, they clone or clean up Git repositories before checkout, so, all uncommitted changes will be ignored.
  To bypass Git checkout and clean up you can specify version *CURRENT*.
  In this case Git repositories are treated like directories.
* *Path* sets either a path relative to :term:`$KLEVER_SRC` or an absolute path to entity (binaries, source files,
  configurations, etc.) or an entity URL.

For some :ref:`klever_addons` it could be necessary to additionally specify *executable path* or/and *python path*
within *path* if binaries or Python packages are not available directly from *path*.
For :ref:`verification_backends` there is also *name* with value *CPAchecker*.
Keep this pair for all specified :ref:`verification_backends`.

Besides, you can set *copy .git directory* and *allow use local Git repository* to *True*.
In the former case deployment scripts will copy directory :file:`.git` if one provides :ref:`klever_addons` as Git
repositories.
In the latter case deployment scripts will use specified Git repositories for cleaning up and checkout required
versions straightforwardly without cloning them to temporary directories.

.. warning:: Setting *allow use local Git repository* to *True* will result in removing all your uncommitted changes!
             Besides, ignore rules from, say, :file:`.gitignore` will be ignored and corresponding files and directories
             will be removed!

*Klever Build Bases* is a JSON object where each pair represents a name of a particular
:ref:`Build Base <klever_build_bases>` and its description as a JSON object.
Each such JSON object should always have some value for *path*:
it should be either an absolute path to the directory that directly contains :ref:`Build Base <klever_build_bases>`,
or an absolute path to the archive with a :ref:`Build Base <klever_build_bases>`,
or a link to the remote archive with a :ref:`Build Base <klever_build_bases>`.
Particular structure of directories inside such archive doesn't matter:
it is only required that there should be a single valid :ref:`Build Base <klever_build_bases>` somewhere inside.
In :file:`job.json` you should specify the name of the :ref:`Build Base <klever_build_bases>`.

.. note:: You can prepare multiple :ref:`deployment configuration files <deploy_conf_file>`, but be careful when using
          them to avoid unexpected results due to tricky intermixes.

.. note:: Actually there may be more :ref:`klever_addons` or :ref:`klever_build_bases` within
          corresponding locations.
          Deployment scripts will consider just described ones.

.. _klever_git_repo_struct:

Structure of Klever Git Repository
----------------------------------

After getting :ref:`klever_addons` and :ref:`klever_build_bases` the Klever Git repository can look as follows:

.. parsed-literal::

    :term:`$KLEVER_SRC`
    ├── addons
    │   ├── cif-1517e57.tar.xz
    │   ├── consul
    │   ├── CPAchecker-1.6.1-svn ea117e2ecf-unix.tar.gz
    │   ├── CPAchecker-35003.tar.xz
    │   ├── toplevel.opt.tar.xz
    │   └── ...
    ├── build bases
    │   ├── linux-3.14.79.tar.xz
    │   └── linux-4.2.6
    │       ├── allmodconfig
    │       └── defconfig
    └── ...

Deployment Variants
-------------------

There are several variants for deploying Klever:

.. toctree::
   :maxdepth: 1

   deploy_local
   deploy_openstack
