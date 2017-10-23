.. Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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

.. _install:

Installation
============

.. _klever-bridge-install:

Klever Bridge installation
--------------------------

PostgreSQL setup
^^^^^^^^^^^^^^^^

#. Trust all local connections by editing :file:`pg_hba.conf` and by restarting the PostgreSQL server::

    $ sudo sed -i '/^local/c\local all all trust' /path/to/pg_hba.conf"

#. Create a new PostgreSQL database (**db_name**)::

    $ createdb -U postgres -T template0 -E utf8 -O postgres db_name

#. Create :file:`bridge/bridge/db.json`:

   .. code-block:: json

      {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "db_name",
        "USER": "postgres"
      }

MySQL/MariaDB setup
^^^^^^^^^^^^^^^^^^^

#. Create a new MySQL/MariaDB user (**db_user**) identified by a password (**db_user_passwd**)::

    MariaDB [(none)]> CREATE USER `db_user`@`localhost` IDENTIFIED BY 'db_user_passwd';

   .. note:: Password can be omitted.

#. Create a new MySQL/MariaDB database (**db_name**) with character set *utf8* and collation *utf8_bin*. Grant full
   access on all its tables to **db_user**::

    MariaDB [(none)]> CREATE DATABASE `db_name` CHARACTER SET utf8 COLLATE utf8_bin;
    MariaDB [(none)]> GRANT ALL ON `db_name`.* TO `db_user`@`localhost`;
    MariaDB [(none)]> FLUSH PRIVILEGES;

#. Create :file:`bridge/bridge/db.json`:

   .. code-block:: json

      {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "db_name",
        "USER": "db_user",
        "PASSWORD": "db_user_passwd",
        "HOST": "127.0.0.1",
        "PORT": "3306"
      }

   .. note:: Password can be omitted if it wasn't set before. Host and port can be omitted if they don't differ from the
             values specified in the example.

Installation for development purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Create :file:`bridge/bridge/settings.py`:

   .. code-block:: python

      from bridge.development import *

#. Execute the following manage.py tasks::

    $ python3 manage.py compilemessages
    $ python3 manage.py migrate
    $ python3 manage.py createsuperuser

   .. note:: Execution of :command:`manage.py migrate` can take quite much time.

#. The last command will prompt you to create a Klever Bridge administrator **klever_bridge_admin** identified by a
   password **klever_bridge_admin_passwd**.
   An email address could be omitted.

#. Run a development server::

    $ python3 manage.py runserver 8998

TOOD: Installation for production purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Create :file:`/var/www/bridge/bridge/settings.py`:

   .. code-block:: python

      from bridge.production import *

Below instructions are given just for Debian (Ubuntu).
Adapt them for your Linux distribution by yourself.

#. Copy Apache2 configuration file :file:`bridge/conf/debian-apache2.conf` to file
   :file:`/etc/apache2/sites-enabled/bridge.conf`.
#. Start listen to port *8998*::

   $ echo "Listen 8998" > /etc/apache2/conf-enabled/bridge.conf

#. Copy directory :file:`bridge` to directory :file:`/var/www/bridge`.

#. Execute the following manage.py task after the ones that are executed during installation for development purposes::

    $ python3 /var/www/bridge/manage.py collectstatic

#. Make *www-data:www-data* owner of directory :file:`/var/www/bridge/media`::

    $ chown -R www-data:www-data /var/www/bridge/media

#. Restart service apache2::

    $ service apache2 restart

Common installation
^^^^^^^^^^^^^^^^^^^

#. Sign in at <http://127.0.0.1:8998/> with username (**klever_bridge_admin**) and password
   (**klever_bridge_admin_passwd**).
#. Populate the database and create a new Klever Bridge Manager (**klever_bridge_manager**) and a new service user
   (**klever_bridge_service_user**).

   .. note:: Population can take quite much time.

#. Either remember passwords generated for them or in addition change these passwords using Admin Tools
   (**klever_bridge_manager_passwd** and **klever_bridge_service_user_passwd** respectively).
#. Sign out and sign in on behalf of **klever_bridge_manager** with password **klever_bridge_manager_passwd**.
#. Enjoy!

Update for development purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Execute the following manage.py tasks::

    $ python3 manage.py compilemessages
    $ python3 manage.py migrate

#. If the last command failed it is recommended to do the following steps.
#. Delete the MySQL/MariaDB database::

    MariaDB [(none)]> DROP DATABASE `db_name`;

#. Create the MySQL/MariaDB database as during normal installation.

   .. note:: The user and its access to this database remain the same from normal installation. You don't need to set up
             them one more time.

#. Repeat all steps of normal installation starting from execution of manage.py tasks (rerunning of the server might be
   not required).

TODO: Update for production purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Klever Core installation
------------------------

Enjoy!

..
   TODO: Install Cloud tools
   -------------------------

   Cloud tools after all requirements installation do not need specific installation, but each tool requires configuration
   file to prepare. All tools have section *common* in corresponfing configuration files. The following configuration
   properties can be set there:

   * *working directory* it is a relative path in the current working directory to create directory for all
     generated files.
   * *keep working directory* implies not to delete existing working directory when running a tool again.
   * *logging* contains configuration properties for `logging <http://docs.python.org/3.4/library/logging.html>`__
     python package.

   Controller configuration
   ^^^^^^^^^^^^^^^^^^^^^^^^

   Prototype for client controller configuration can be found in :file:`Cloud/conf/controller.json`. It is recommended to
   set up manually the following configuration properties:

   * *Klever Bridge* section contains *name*, *user*, *password* attributes which should be set according to Klever Bridge
     service user.
   * *client-controller* section contains consul configuration properties and an absoulute path to a directory with consul
     binary and directory with web-UI files in it.
     It is better to provide your own *Klever Bridge* service check and turn-on or off consul web-UI.
   * *node configuration* section contains configuration options which tell a controller which resources of your computer
     are available for a scheduler. It is recommended to leave enough RAM memory for the other programms running on the
     computer and to choose partition with enough disk space before running controller.

   Scheduler configuration
   ^^^^^^^^^^^^^^^^^^^^^^^

   Prototype for scheduler configuration can be found in :file:`Cloud/conf/scheduler.json`. It is recommended to set up
   manually the following configuration properties:

   * *Klever Bridge* section contains *name*, *user*, *password* attributes which should be set according to Klever Bridge
     service user.
   * *Scheduler* section describes scheduling configuration with the following major attributes:
       * *controller address* - address which is used to access consul (do not change it if you use default consul
         configuration).
       * *keep working directory* attribute implies not to delete generated working directories.
         If you are going to debug Klever Core or a verification tool it is recommended to set it as *true*, but it will
         cause problems in case of solving the same job or task twice.
       * *job client configuration*/*task client configuration* attribute corresponds to an absolute path to a file with
         job/task client configuration (see below).
       * *"verification tools"* contains names of verification tools, corresponding versions and absolute pathes to
         binaries of corresponding verification tools.

   Scheduler job/task client configuration
   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

   Prototype for scheduler job/task client configuration can be found in :file:`Cloud/conf/job-client.json`/
   :file:`Cloud/conf/task-client.json`.
   It is recommended to set up manually the following configuration properties:

   * *client:benchexec location* configuration property corresponds to an absolute path to a root directory with
     downloaded BenchExec sources.
   * for jobs:

     * *client:cif location* configuration property corresponds to an absolute path to a binaries directory with CIF tools.
     * *client:cil location* configuration property corresponds to an absolute path to a binaries directory with CIL tools.

   * for tasks:

     * *client:cif location* configuration property corresponds to an absolute path to a binaries directory with CIF tools.
     * *client:cil location* configuration property corresponds to an absolute path to a binaries directory with CIL tools.
