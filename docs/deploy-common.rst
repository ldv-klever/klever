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

* `Python 3.4 or higher <https://www.python.org/>`__ (if you build Python from source, you need to install development
  files for `xz <https://tukaani.org/xz/>`__ in advance).
* `tar <https://www.gnu.org/software/tar/>`__,
  `gz <https://www.gnu.org/software/gzip/>`__,
  `bzip2 <http://www.bzip.org/>`__,
  `xz <https://tukaani.org/xz/>`__,
  `unzip <http://infozip.sourceforge.net/UnZip.html>`__,
  `git <https://git-scm.com/>`__ and
  `wget <https://www.gnu.org/software/wget/>`__
  (if you are going to deploy entities from corresponding sources).

To deploy Klever one has to clone its Git repository (a path to a directory where it is cloned is referred to as
:term:`$KLEVER_SRC`)::

    git clone --recursive https://forge.ispras.ru/git/klever.git

.. note:: Alternatively one can use https://github.com/ldv-klever/klever.git.

Then one has to get :ref:`klever_addons` and :ref:`klever_build_bases`.
Both of them should be described appropriately within :ref:`deploy_conf_file`.

.. note:: You can omit getting :ref:`klever_addons` if you will use
          :file:`deploys/conf/klever-minimal.json.sample` from :term:`$KLEVER_SRC` as :ref:`deploy_conf_file` since it
          contains URLs for all required :ref:`klever_addons`.

.. _klever_addons:

Klever Addons
-------------

You can provide :ref:`klever_addons` in various forms:

* Local files, directories, archives or Git repositories.
* Remote files, archives or Git repositories.

Deployment scripts will take care of their appropriate extracting.
The best place for :ref:`klever_addons` is directory :file:`addons` within :term:`$KLEVER_SRC` (see
:ref:`klever_git_repo_struct`).

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
`here <https://forge.ispras.ru/attachments/download/6780/cif-d09b7a5.tar.xz>`__.
These binaries are compatible with various Linux distributions since CIF is based on `GCC <https://gcc.gnu.org/>`__
that has few dependencies.
Besides, one can clone `CIF Git repository <https://forge.ispras.ru/projects/cif/repository>`__ and build CIF from
source using corresponding instructions.

.. _cil:

Frama-C (CIL)
^^^^^^^^^^^^^

You can get `Frama-C (CIL) <https://frama-c.com/>`__ binaries from
`here <https://forge.ispras.ru/attachments/download/7049/frama-c-cil-8ded734.tar.xz>`__.
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
You can download binaries of CPAchecker suitable for checking most of requirements from
`here https://forge.ispras.ru/attachments/download/6427/CPAchecker-1.8-svn 31140-unix.tar.xz>`__.
For finding data races additionally download binaries of another custom version of CPAchecker from
`here <https://forge.ispras.ru/attachments/download/5871/CPAchecker-1.7-svn  28916-unix.tar.gz>`__.
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
All :ref:`klever_build_bases` should be provided as directories or archives.
Any of these directories can contain multiple :ref:`klever_build_bases` placed within appropriate intermediate
directories.
Archives should contain :file:`meta.json` directly at the top level without any intermediate directories.
The best place for :ref:`klever_build_bases` is directory :file:`build bases` within :term:`$KLEVER_SRC` (see
:ref:`klever_git_repo_struct`).

.. note:: Git does not track :file:`build bases` from :term:`$KLEVER_SRC`.

.. _deploy_conf_file:

Deployment Configuration File
-----------------------------

After getting :ref:`klever_addons` and :ref:`klever_build_bases` one needs to describe them within
:ref:`deploy_conf_file`.
First we recommend to copy :file:`deploys/conf/klever-minimal.json.sample` from :term:`$KLEVER_SRC` to some JSON file
within :file:`deploys/conf/` from :term:`$KLEVER_SRC` (see :ref:`klever_git_repo_struct`).
Since deployment scripts use :file:`deploys/conf/klever.json` from :term:`$KLEVER_SRC` by default this is the best place
for that file.

.. note:: Git does not track :file:`deploys/conf/*.json` from :term:`$KLEVER_SRC`.

.. note:: :file:`deploys/conf/klever-minimal.json.sample` from :term:`$KLEVER_SRC` is so consize as possible.
          One can find much more examples for describing :ref:`klever_addons` and :ref:`klever_build_bases` in
          :file:`deploys/conf/klever-deploy-means.json.sample` from :term:`$KLEVER_SRC`.

Then you need to fix the sample to describe Klever and all required :ref:`klever_addons` and :ref:`klever_build_bases`.
Generally there are 3 pairs within :ref:`deploy_conf_file` with names *Klever*, *Klever Addons* and *Klever Build Bases*
correspondingly.
The first one directly represents a JSON object describing Klever.
The second one is a JSON object where each pair represents a name of a particular :ref:`Klever addon <klever_addons>`
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
  Also, they clone or clean up Git repositories before checkouting, so, all uncommited changes will be ignored.
  To bypass Git checkouting and clean up you can specify version *CURRENT*.
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
In the latter case deployment scripts will use specified Git repositories for cleaning up and checkouting required
versions straightforwardly without cloning them to temporary directories.

.. warning:: Setting *allow use local Git repository* to *True* will result in removing all your uncommited changes!
             Besides, ignore rules from, say, :file:`.gitignore` will be ignored and corresponding files and directories
             will be removed!

:ref:`klever_build_bases` should be specified either as directories with one or more :ref:`klever_build_bases` or as
archives each of which should contain exactly one Klever build base.
In :file:`job.json` you should specify basenames of these archives or paths to subdirectories with
:file:`meta.json` of corresponding :ref:`klever_build_bases` relatively to directories including their names.

.. note:: You can prepare multiple :ref:`deployment configuration files <deploy_conf_file>`, but be careful when using
          them to avoid unexpected results due to tricky intermixes.

.. note:: Actually there may be more :ref:`klever_addons` or :ref:`klever_build_bases` within
          corresponding locations.
          Deployment scripts will consider just described ones.

.. _klever_git_repo_struct:

Structure of Klever Git Repository
----------------------------------

After :ref:`deploy_common` the Klever Git repository can look as follows:

.. parsed-literal::

    :term:`$KLEVER_SRC`
    ├── addons
    │   ├── cif-1517e57.tar.xz
    │   ├── consul
    │   ├── CPAchecker-1.6.1-svn ea117e2ecf-unix.tar.gz
    │   ├── CPAchecker-1.8-svn 31140-unix.tar.xz
    │   ├── toplevel.opt.tar.xz
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
    ├── build bases
    │   ├── linux-3.14.79.tar.xz
    │   └── ...
    └── ...
