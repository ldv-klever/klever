.. _install:

Installation
============

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

#. Proceed with either :ref:`dev-install` or :ref:`production-install`.
#. Sign in at `<http://127.0.0.1:8998/>`_ with username (**omega_admin**) and password (**omega_admin_passwd**).
#. Create a new Omega manager (**omega_manager**).
#. Remember his/her password (**omega_manager_passwd**).
#. Sign out and sign in on behalf of **omega_manager**.
#. Enjoy!

.. _dev-install:

Installation for development purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Run a development server::

    $ python3 manage.py runserver 8998

.. _production-install:

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
    $ python3 manage.py makemigrations users jobs reports marks service
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

Documentation installation
--------------------------

#. Execute the following command (it should be executed each time when documentation might be changed)::

    $ make -C docs html

#. Find the generated documenation index in :file:`docs/_build/index.html`.
