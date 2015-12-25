.. _install:

Installation
============

Documentation installation
--------------------------

#. Execute the following command (it should be executed each time when documentation might be changed)::

    $ make -C docs html

#. Open generated documenation index :file:`docs/_build/index.html`.

.. _klever-bridge-install:

Klever Bridge installation
--------------------------

#. Create a new MySQL/MariaDB user (**db_user**) identified by a password (**db_user_passwd**)::

    MariaDB [(none)]> CREATE USER `db_user`@`localhost` IDENTIFIED BY 'db_user_passwd';

#. Create a new MySQL/MariaDB database (**db_name**) with character set utf8 and grant full access on all its tables to
   **db_user**::

    MariaDB [(none)]> CREATE DATABASE `db_name` CHARACTER SET utf8;
    MariaDB [(none)]> GRANT ALL ON `db_name`.* TO `db_user`@`localhost`;
    MariaDB [(none)]> FLUSH PRIVILEGES;

#. Create :file:`bridge/bridge/mysql-db.cnf`::

    [client]
    database = db_name
    user = db_user
    password = db_user_passwd
    default-character-set = utf8

#. Execute the following manage.py tasks::

    $ python3 manage.py compilemessages
    $ python3 manage.py makemigrations jobs marks reports service users
    $ python3 manage.py migrate
    $ python3 manage.py createsuperuser

   .. note:: Execution of :command:`manage.py migrate` can take quite much time.

#. The last command will prompt you to create a Klever Bridge administrator **klever_bridge_admin** identified by a
   password **klever_bridge_admin_passwd**.
   An email address could be omitted.
#. Proceed with either :ref:`klever-bridge-dev-install` or :ref:`klever-bridge-production-install`.
#. Sign in at `<http://127.0.0.1:8998/>`_ with username (**klever_bridge_admin**) and password
   (**klever_bridge_admin_passwd**).
#. Create a new Klever Bridge Manager (**klever_bridge_manager**) and a new service user
   (**klever_bridge_service_user**).
#. Remember their passwords (**klever_bridge_manager_passwd** and **klever_bridge_service_user_passwd** respectively).
#. Sign out and sign in on behalf of **klever_bridge_manager** with password **klever_bridge_manager_passwd**.
#. Enjoy!

.. _klever-bridge-dev-install:

Installation for development purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Run a development server::

    $ python3 manage.py runserver 8998

.. _klever-bridge-production-install:

Installation for production purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Below instructions are given just for Debian (Ubuntu).
Adapt them for your Linux distribution by yourself.

#. Copy Apache2 configuration file :file:`bridge/conf/debian-apache2.conf` to file
   :file:`/etc/apache2/sites-enabled/bridge.conf`.
#. Start listen to port *8998*::

   $ echo "Listen 8998" > /etc/apache2/conf-enabled/bridge.conf

#. Copy directory :file:`bridge` to directory :file:`/var/www/bridge`.
#. Replace content of file :file:`/var/www/bridge/bridge/settings.py` with *from bridge.production import **::

    $ echo "from bridge.production import *" > /var/www/bridge/bridge/settings.py

#. Execute the following manage.py task::

    $ python3.4 /var/www/bridge/manage.py collectstatic

#. Create directory :file:`/var/www/bridge/media` and make www-data:www-data its owner::

    $ mkdir -p /var/www/bridge/media
    $ chown -R www-data:www-data /var/www/bridge/media

#. Restart service apache2::

    $ service apache2 restart

Update for development purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Execute the following manage.py tasks::

    $ python3 manage.py compilemessages
    $ python3 manage.py makemigrations jobs marks reports service users
    $ python3 manage.py migrate

#. If some of previous commands failed it is recommended to do the following steps.
#. Remove previously created migrations::

    find ./ -name "migrations" | xargs -n1 rm -rf

#. Recreate the MySQL/MariaDB database::

    MariaDB [(none)]> DROP DATABASE `db_name`;
    MariaDB [(none)]> CREATE DATABASE `db_name` CHARACTER SET utf8;

#. Repeat all steps of normal installation starting from execution of manage.py tasks (rerunning of the server might be
   not required).

TODO: Update for production purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Klever Core installation
------------------------

Enjoy!

TODO: Install Cloud tools
-------------------------

Cloud tools after all requirements installation do not need specific installation, but each tool requires configuration
file to prepare. All tools have section *common* in corresponfing configuration files. The following configuration
properties can be set there:

* *working directory* it is a relative path in the current working directory to create directory for all
  generated files.
* *keep working directory* implies not to delete existing working directory when running a tool again.
* *logging* contains configuration properties for `logging <http://docs.python.org/3.4/library/logging.html>`_
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
