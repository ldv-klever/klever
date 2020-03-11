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

To accomplish local deployment of Klever you need to choose an appropriate mode (one should select *development* only
for development purposes, otherwise, please, choose *production*) and to run the following command within
:term:`$KLEVER_SRC`:

.. parsed-literal::

    $ sudo :term:`$KLEVER_SRC`/venv/bin/klever-deploy-local --deployment-directory :term:`$KLEVER_DEPLOY_DIR` install production

.. note:: Absolute path to :file:`klever-deploy-local` is necessary due to environment variables required for the
          Klever Python virtual environment are not passed to sudo commands most likely.

After successfull installation one is able to *update* Klever multiple times to install new or to update alredy
installed :ref:`klever_addons` and :ref:`klever_build_bases`:

.. parsed-literal::

    $ sudo :term:`$KLEVER_SRC`/venv/bin/klever-deploy-local --deployment-directory :term:`$KLEVER_DEPLOY_DIR` update production

To *uninstall* Klever, e.g. if something went wrong during installation, you need to run:

.. parsed-literal::

    $ sudo :term:`$KLEVER_SRC`/venv/bin/klever-deploy-local --deployment-directory :term:`$KLEVER_DEPLOY_DIR` uninstall production

A normal sequence of actions for :ref:`local_deploy` is the following:
:menuselection:`install --> update --> update --> ... --> update --> uninstall`.
In addition, there are several optional command-line arguments which you can find out by running::

    $ klever-deploy-local --help

We strongly recommend to configure your file indexing service if you have it enabled so that it will ignore content of
:term:`$KLEVER_DEPLOY_DIR`.
Otherwise, it can consume too much computational resources since Klever manipulates files very extensively during its
operation.
To do this, please, refer to an appropriate user documentation.
