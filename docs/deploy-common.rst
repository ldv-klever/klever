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

:orphan:

.. _deploy_common:

Common Deployment
=================

To execute deployment scripts you need to install:

* `Python 3.4 or higher <https://www.python.org/>`_.
* `tar <https://www.gnu.org/software/tar/>`__,
  `gz <https://www.gnu.org/software/gzip/>`__,
  `bzip2 <http://www.bzip.org/>`__,
  `xz <https://tukaani.org/xz/>`__ and
  `git <https://git-scm.com/>`__
  (if you are going to deploy entities from corresponding sources).

To deploy Klever one has to clone its Git repository (below a path to a directory where it is cloned is referred to as
*$KLEVER_SRC*)::

    git clone --recursive https://forge.ispras.ru/git/klever.git

Then one has to get :ref:`klever_addons` and perhaps :ref:`target_software`.
Both of them should be described appropriately within :ref:`deploy_conf_file`.

.. _klever_addons:

Klever Addons
-------------

You can provide :ref:`klever_addons` in various forms such as files, directories, archives or Git repositories.
Deployment scripts will take care of their appropriate extracting.
At the moment everything should be local, e.g. you can not specify an URL for a Git repository.
The best place for :ref:`klever_addons` is directory :file:`addons` within *$KLEVER_SRC* (see
:ref:`klever_git_repo_struct`).

.. note:: Git does not track :file:`$KLEVER_SRC/addons`.

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
`here <https://forge.ispras.ru/attachments/5738/cif-d95cdf0.tar.gz>`__.
These binaries are compatible with various Linux distributions since CIF is based on `GCC <https://gcc.gnu.org/>`__
that has few dependencies.
Besides, one can clone `CIF Git repository <https://forge.ispras.ru/projects/cif/repository>`__ and build CIF from
source using corresponding instructions.

.. _cil:

CIL
^^^

`CIL <https://people.eecs.berkeley.edu/~necula/cil/>`__ is a very legacy Klever addon.
You can get its binaries from `here <https://forge.ispras.ru/attachments/5739/cil-1.5.1.tar.gz>`__.
As well, you can build it from
`this source <https://forge.ispras.ru/projects/cil/repository/revisions/fdae07e10fcab22c59e30813d87aa5401ef1e7fc>`__
which has several specific patches relatively to the mainline.

.. _consul:

Consul
^^^^^^

One can download appropriate `Consul <https://www.consul.io/>`__ binaries from
`here <http://www.consul.io/downloads.html>`__.
We are successfully using version 0.9.2 but new versions can also be fine.
It is possible to build Consul from `source <https://github.com/hashicorp/consul>`__.

.. _verification_backends:

Verification Backends
^^^^^^^^^^^^^^^^^^^^^

You need at least one tool that will perform actual verification of your software.
These tools are referred to as :ref:`verification_backends`.
As verification backends Klever supports `CPAchecker <https://cpachecker.sosy-lab.org/>`__ well.
Some other verification backends are supported experimentally and currently we do not recommend to use them.
You can download binaries of CPAchecker suitable for checking most of requirements from
`here <https://forge.ispras.ru/attachments/5740/CPAchecker-1.7-svn%2027946-unix.tar.gz>`__.
For finding data races additionally download binaries of another custom version of CPAchecker from
`here <https://forge.ispras.ru/attachments/5741/CPAchecker-1.6.1-svn%20ea117e2ecf-unix.tar.gz>`__.
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

.. _target_software:

Target Software
---------------

Like :ref:`klever_addons` one can provide :ref:`target_software` to be verified.
At the moment this is only the `Linux kernel <https://www.kernel.org/>`__.
Providing source code of :ref:`target_software` at this stage can quite considerably reduce overall verification time.
The best place for :ref:`target_software` is directory :file:`programs` within *$KLEVER_SRC* (see
:ref:`klever_git_repo_struct`).

.. note:: Git does not track :file:`$KLEVER_SRC/programs`.

.. _deploy_conf_file:

Deployment Configuration File
-----------------------------

After getting :ref:`klever_addons` and :ref:`target_software` one needs to describe them within
:ref:`deploy_conf_file`.
First we recommend to copy :file:`$KLEVER_SRC/deploys/conf/klever-minimal.json.sample` to some JSON file within
:file:`$KLEVER_SRC/deploys/conf/` (see :ref:`klever_git_repo_struct`).
Since deployment scripts use :file:`$KLEVER_SRC/deploys/conf/klever.json` by default this is the best place for that
file.

.. note:: Git does not track :file:`$KLEVER_SRC/deploys/conf/*.json`.

.. note:: :file:`$KLEVER_SRC/deploys/conf/klever-minimal.json.sample` is so consize as possible.
          One can find much more examples for describing various entities in
          :file:`$KLEVER_SRC/deploys/conf/klever-deploy-means.json.sample`

Then you need to fix the sample to describe Klever and all required :ref:`klever_addons` and :ref:`target_software`.
Generally there are 3 pairs within :ref:`deploy_conf_file` with names *Klever*, *Klever Addons* and *Programs*
correspondingly.
The first one directly represents a JSON object describing Klever.
The second and the third ones are JSON objects where each pair represents a name of a particular
:ref:`Klever addon <klever_addons>` or :ref:`target_software` and its description as a JSON object.
There is the only exception.
Within *Klever Addons* there is *Verification Backends* that serves for describing :ref:`verification_backends`.

Each JSON object that describes an entity should always have values for *version* and *path*:

* *Version* gives a very important knowledge for deployment scripts.
  Depending on values of this pair they behave appropriately.
  When entities are represented as files, directories or archives deployment scripts remember versions of
  installed/updated entities.
  So, later they update these entities just when their versions change.
  For Git repositories versions can be anything suitable for a `Git checkout <https://git-scm.com/docs/git-checkout>`__,
  e.g. appropriate Git branches, tags or commits.
  In this case deployment scripts checkout specified versions first.
  Also, they clone or clean up Git repositories before checkouting, so, all uncommited changes will be ignored.
  To bypass Git checkouting and clean up you can specify version *CURRENT*.
  In this case Git repositories are treated like directories.
* *Path* sets either a path relative to :file:`$KLEVER_SRC` or an absolute path to entity (binaries, source files,
  configurations, etc.).
  As we mentioned above you can specify individual files, directories, archives and Git repositories as paths.

For some :ref:`klever_addons` it could be necessary to additionally specify *executable path* within *path* if binaries
are not available directly from *path*.
For :ref:`verification_backends` there is also *name* with value *CPAchecker*.
Keep this pair for all specified :ref:`verification_backends`.

For :ref:`target_software` you can additionally set *copy .git directory* and *allow use local Git repository* to *True*.
In the former case deployment scripts will copy directory :file:`.git` if one provides :ref:`target_software` as Git
repositories.
This can be necessary for verifying commits from Git repositories.
In the latter case deployment scripts will use specified Git repositories for cleaning up and checkouting required
versions straightforwardly without cloning them to temporary directories.

.. warning:: Setting *allow use local Git repository* to *True* will result in removing all your uncommited changes!
             Besides, ignore rules from, say, :file:`.gitignore` will be ignored and corresponding files and directories
             will be removed!

.. note:: You can prepare multiple :ref:`deployment configuration files <deploy_conf_file>`, but be careful when using
          them to avoid unexpected results due to tricky intermixes.

.. note:: Actually there may be more :ref:`klever_addons` or :ref:`target_software` within
          corresponding locations.
          Deployment scripts will consider just described ones.

.. _klever_git_repo_struct:

Structure of Klever Git Repository
----------------------------------

After :ref:`deploy_common` the Klever Git repository can look as follows:

.. code::

    $KLEVER_SRC
    ├── addons
    │   ├── cif-d95cdf0.tar.gz
    │   ├── cil-1.5.1.tar.gz
    │   ├── consul
    │   ├── CPAchecker-1.6.1-svn ea117e2ecf-unix.tar.gz
    │   ├── CPAchecker-1.7-svn 27946-unix.tar.gz
    │   └── ...
    ├── deploys
    │   ├── bin
    │   │   ├── deploy-local
    │   │   └── deploy-openstack
    │   ├── conf
    │   │   ├── klever.json
    │   │   ├── klever-deploy-means.json.sample
    │   │   └── klever-minimal.json.sample
    │   └── ...
    ├── programs
    │   ├── linux-3.14.tar.xz
    │   ├── linux-stable
    │   └── ...
    └── ...
