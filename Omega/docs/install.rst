.. _install:

Installation
============

#. Create a new MySQL user (**mysql_user**) identified by a password (**mysql_passwd**).
#. Create a new MySQL database (**mysql_db**) and grant full access on all its tables to **mysql_user**.
#. Create :file:`Omega/db.cnf`::

    [client]
    database = mysql_db
    user = mysql_user
    password = mysql_passwd
    default-character-set = utf8

#. Execute the following manage.py tasks::

    $ python3.4 manage.py compilemessages
    $ python3.4 manage.py makemigrations users jobs reports marks
    $ python3.4 manage.py migrate

#. Proceed with either :ref:`dev-install` or :ref:`production-install`.

.. _dev-install:

Installation for development purposes
-------------------------------------

#. Run a development server::

    $ python3.4 manage.py runserver

#. Register a new Omega user (**omega_user**) in a browser at `<http://127.0.0.1:8000>`_.
#. Stop the server by pressing :kbd:`Control-c` in the console where :program:`runserver` was executed.
#. Open a Python shell::

    $ python3.4 manage.py shell

#. Execute the following commands in the Python shell::

     >>> import jobs.populate
     >>> jobs.populate.main_population('omega_user')

#. Stop the Python shell by pressing :kbd:`Control-d`.
#. Run the development server once again.
#. Enjoy!

.. _production-install:

Installation for production purposes
------------------------------------

.. todo:: please describe me!

Documentation installation
--------------------------

#. Execute the following command::

    $ make -C docs html

#. Find the generated documenation index in :file:`docs/_build/index.html`.
