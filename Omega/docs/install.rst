.. _install:

Installation
============

Omega installation
------------------

#. Create a new MySQL user (**mysql_user**) identified by a password (**mysql_passwd**).
#. Create a new MySQL database (**mysql_db**) with character set utf8 and grant full access on all its tables to **mysql_user**.
#. Create :file:`Omega/Omega/db.cnf`::

    [client]
    database = mysql_db
    user = mysql_user
    password = mysql_passwd
    default-character-set = utf8

#. Execute the following manage.py tasks::

    $ python3.4 manage.py compilemessages
    $ python3.4 manage.py makemigrations users jobs reports marks service
    $ python3.4 manage.py migrate
    $ python3.4 manage.py createsuperuser

#. With last command you will create **omega_user** identified by a password **omega_passwd**.
#. Proceed with either :ref:`dev-install` or :ref:`production-install`.

.. _dev-install:

Installation for development purposes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Run a development server::

    $ python3.4 manage.py runserver

#. Enjoy!

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
#. Edit :file:`Omega/Omega/settings.py`::
    #. Comment lines: 26, 30, 94, 127
    #. Uncomment lines: 28, 32, 95-98, 129 and update it::

        'NAME': '**mysql_db**',
        'USER': '**mysql_user**',
        'PASSWORD': '**mysql_passwd**',

#. Execute the following manage.py task::

    $ python3.4 manage.py collectstatic

#. Restart service apache2
#. Enjoy `<http://127.0.0.1/>`_!

Documentation installation
--------------------------

#. Execute the following command::

    $ make -C docs html

#. Find the generated documenation index in :file:`docs/_build/index.html`.
