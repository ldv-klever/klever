.. _install:

Installation
============

Documentation installation
--------------------------

#. Execute the following command (it should be executed each time when documentation might be changed)::

    $ make -C docs html

#. Find the generated documenation index in :file:`docs/_build/index.html`.

.. _omega-install:

Omega installation
------------------

#. Create a new MySQL/MariaDB user (**db_user**) identified by a password (**db_user_passwd**)::

    MariaDB [(none)]> CREATE USER `db_user`@`localhost` IDENTIFIED BY 'db_user_passwd';

#. Create a new MySQL/MariaDB database (**db_name**) with character set utf8 and grant full access on all its tables to
   **db_user**::

    MariaDB [(none)]> CREATE DATABASE `db_name` CHARACTER SET utf8;
    MariaDB [(none)]> GRANT ALL ON `db_name`.* TO `db_user`@`localhost`;
    MariaDB [(none)]> FLUSH PRIVILEGES;

#. Create :file:`Omega/Omega/db.cnf`::

    [client]
    database = db_name
    user = db_user
    password = db_user_passwd
    default-character-set = utf8

#. Execute the following manage.py tasks::

    $ python3 manage.py compilemessages
    $ python3 manage.py makemigrations users jobs reports marks service
    $ python3 manage.py migrate
    $ python3 manage.py createsuperuser

   .. note:: Execution of :command:`manage.py migrate` can take quite much time.

#. The last command will prompt you to create an Omega administrator **omega_admin** identified by a password
   **omega_admin_passwd**.
   An email address could be omitted.

#. Proceed with either :ref:`omega-dev-install` or :ref:`omega-production-install`.
#. Sign in at `<http://127.0.0.1:8998/>`_ with username (**omega_admin**) and password (**omega_admin_passwd**).
#. Create a new Omega Manager (**omega_manager**) and a new service user (**omega_service_user**).
#. Remember their passwords (**omega_manager_passwd** and **omega_service_user_passwd** respectively).
#. Sign out and sign in on behalf of **omega_manager**.
#. Enjoy!

.. _omega-dev-install:

Installation for development purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Run a development server::

    $ python3 manage.py runserver 8998

.. _omega-production-install:

Installation for production purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Add to the file :file:`/etc/apache2/sites-available/000-default.conf` next lines::

    WSGIScriptAlias / /var/www/Omega/Omega/wsgi.py
    WSGIDaemonProcess localhost python-path=/var/www/Omega
    WSGIProcessGroup localhost
    <Directory /var/www/Omega/Omega>
        <Files wsgi.py>
            Require all granted
        </Files>
    </Directory>

    Alias /static/ /var/www/Omega/static/
    <Location "/static/">
        Options -Indexes
    </Location>

    Alias /media/ /var/www/Omega/media/
    <Location "/media/">
        Options -Indexes -FollowSymLinks -Includes -ExecCGI
        Allowoverride All
        Require all granted
        Allow from all
    </Location>

#. Copy Omega to :file:`/var/www/`
#. Create path: :file:`/var/www/Omega/media/` and make www-data owner of the new folder.
#. Edit :file:`Omega/Omega/settings.py`:

   * Comment lines: 26, 30, 123.
   * Uncomment lines: 28, 32, 125.

#. Execute the following manage.py task::

    $ python3.4 manage.py collectstatic

#. Restart service apache2

Update for development purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Execute the following manage.py tasks::

    $ python3 manage.py compilemessages
    $ python3 manage.py makemigrations users jobs reports marks service tools
    $ python3 manage.py migrate

#. If some of previous commands failed it is recommended to do the following steps.
#. Remove previously created migrations::

    find ./ -name "migrations" | xargs -n1 rm -rf

#. Recreate the MySQL/MariaDB database::

    MariaDB [(none)]> DROP DATABASE `db_name`;
    MariaDB [(none)]> CREATE DATABASE `db_name` CHARACTER SET utf8;

#. Repeat all steps of normal installation starting from execution of manage.py tasks (rerunning of the server might be
   not required).

Update for production purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. TODO: how to update production server?

Install Cloud tools
-------------------

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

* *Omega* section contains *name*, *user*, *password* attributes which should be set according to Omega service user.
* *client-controller* section contains consul configuration properties and an absoulute path to a directory with consul
  binary and directory with web-UI files in it. It is better to provide your own *Omega* service check and turn-on or
  off consul web-UI.
* *node configuration* section contains configuration options which tell a controller which resources of your computer
  are available for a scheduler. It is recommended to leave enough RAM memory for the other programms running on the
  computer and to choose partition with enough disk space before running controller.

Scheduler configuration
^^^^^^^^^^^^^^^^^^^^^^^

Prototype for scheduler configuration can be found in :file:`Cloud/conf/scheduler.json`. It is recommended to set up
manually the following configuration properties:

* *Omega* section contains *name*, *user*, *password* attributes which should be set according to Omega service user.
* *Scheduler* section describes scheduling configuration with the following major attributes:
    * *controller address* - address which is used to access consul (do not change it if you use default consul
      configuration).
    * *keep working directory* attribute implies not to delete generated working directories. If you are going to debug psi or
      a verification tool it is recommended to set it as *true*, but it will cause problems in case of solving the same
      job or task twice.
    * *job client configuration* attribute corresponds to an absolute path to a file with client configuration. You can
      prepare such file on the base of :file:`Cloud/conf/client.json`.
    * *"verification tools"* contains names of verification tools, corresponding versions and absolute pathes to
      binaries of corresponding verification tools.

Scheduler client configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Prototype for scheduler client configuration can be found in :file:`Cloud/conf/client.json`. It is recommended to set
up manually the following configuration properties:

* *client:benchexec location* configuration property corresponds to an absolute path to a root directory with
  downloaded BenchExec sources.
* *client:cif location* configuration property corresponds to an absolute path to a binaries directory with CIF tools.

Psi installlation
-----------------

Enjoy!
