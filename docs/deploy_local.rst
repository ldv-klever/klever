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

.. _local_deploy:

Local Deployment
================

.. warning:: Do not deploy Klever at your workstation or valuable servers unless you are ready to lose some sensitive
             data or to have misbehaved software.

.. warning:: Currently deployment on Fedora makes the *httpd_t* SELinux domain permissive, which may negatively impact
             the security of your system.

To accomplish local deployment of Klever you need to choose an appropriate mode (one should select *development* only
for development purposes, otherwise, please, choose *production*) and to run the following command within
:term:`$KLEVER_SRC`:

.. code-block:: console

  $ sudo venv/bin/klever-deploy-local --deployment-directory $KLEVER_DEPLOY_DIR install production

.. note:: Absolute path to :file:`klever-deploy-local` is necessary due to environment variables required for the
          Klever Python virtual environment are not passed to sudo commands most likely.

.. note:: You should install Klever Python package in the editable mode in case of the development mode
          (:ref:`software_requirements`). Otherwise, some functionality may not work as intended.

After successful installation one is able to *update* Klever multiple times to install new or to update already
installed :ref:`klever_addons` and :ref:`klever_build_bases`:

.. code-block:: console

  $ sudo venv/bin/klever-deploy-local --deployment-directory $KLEVER_DEPLOY_DIR update production

If you need to update Klever Python package itself (e.g. this may be necessary after update of :term:`$KLEVER_SRC`),
then you should execute one additional command prior to the above one:

.. code-block:: console

  $ pip install --upgrade .

This additional command, however, should be skipped if Klever Python package was installed in the *editable* mode (with
flag -e) unless you need to to upgrade Klever dependencies.
In the latter case you should execute the following command prior updating Klever:

.. code-block:: console

  $ pip install --upgrade -e .

To *uninstall* Klever you need to run:

.. code-block:: console

  $ sudo venv/bin/klever-deploy-local --deployment-directory $KLEVER_DEPLOY_DIR uninstall production

A normal sequence of actions for :ref:`local_deploy` is the following:
:menuselection:`install --> update --> update --> ... --> update --> uninstall`.
In addition, there are several optional command-line arguments which you can find out by running:

.. code-block:: console

  $ klever-deploy-local --help

We strongly recommend to configure your file indexing service if you have it enabled so that it will ignore content of
:term:`$KLEVER_DEPLOY_DIR`.
Otherwise, it can consume too much computational resources since Klever manipulates files very extensively during its
operation.
To do this, please, refer to an appropriate user documentation.

Troubleshooting
---------------

If something went wrong during installation, you need to uninstall Klever completely prior to following attempts to
install it.
In case of ambiguous issues in the development mode you should try to remove the virtual environment and to create it
from scratch.

On Astra Linux, it is necessary to set the parameter ``zero_if_notfound: yes`` in the file
:file:`etc/parsec/mswitch.conf`, otherwise there will be an error connecting to the database like
``error obtaining MAC configuration for user ...``.