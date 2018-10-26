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

.. _local_deploy:

Local Deployment
================

.. warning:: Do not deploy Klever at your workstation or valuable servers unless you are ready to lose some sensitive
             data or to have misbehaved software.
             We hope that one day Klever will be more safe and secure, so this warning will be redundant.

:ref:`local_deploy` works for `Debian 9 <https://wiki.debian.org/DebianStretch>`__.
Also, you can try it for other versions of Debian as well as for various
`Debian derivatives <https://wiki.debian.org/Derivatives/>`__, e.g. it works for
`Ubuntu 18.04 <https://wiki.ubuntu.com/BionicBeaver/ReleaseNotes>`__ as well.

Prior to proceding to :ref:`local_deploy`, it is necessary to perform :ref:`deploy_common`.
Then you need to choose an appropriate deployment mode.
One should select *development* only if one is going to develop Klever (see :ref:`dev_deploy` in addition).
Otherwise, please, choose *production*.
Then you should *install* Klever::

    $ sudo $KLEVER_SRC/deploys/bin/deploy-local --deployment-directory $KLEVER_DEPLOY_DIR install production

After successfull installation one is able to *update* Klever multiple times to install new or to update alredy
installed :ref:`klever_addons` and :ref:`klever_build_bases` as well as to update Klever itself::

    $ sudo $KLEVER_SRC/deploys/bin/deploy-local --deployment-directory $KLEVER_DEPLOY_DIR update production

To *uninstall* Klever, e.g. if something went wrong during installation, you need to run::

    $ sudo $KLEVER_SRC/deploys/bin/deploy-local --deployment-directory $KLEVER_DEPLOY_DIR uninstall production

So that a normal sequence of actions for :ref:`local_deploy` is the following:
":menuselection:`install --> update --> update --> ... --> update --> uninstall`".
In addition, there are several optional arguments which you can find out by running::

    $ $KLEVER_SRC/deploys/bin/deploy-local --help
