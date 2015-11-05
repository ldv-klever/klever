Requirements
============

To run Omega you need:

* `Python 3.4.x <https://www.python.org/>`_ and its packages:

  * `Django <https://www.djangoproject.com/>`_.
  * `pytz <http://pythonhosted.org/pytz/>`_.
  * `mysqlclient <https://github.com/PyMySQL/mysqlclient-python>`_ (requires Python and MySQL development headers and libraries).

* `MySQL <https://www.mysql.com/>`_/`MariaDB <https://mariadb.org/>`_ (server).

To run a production server you additionally need:

* `apache2 <http://httpd.apache.org/>`_ and its module `mod_wsgi <https://code.google.com/p/modwsgi/>`_.

To translate Omega (i.e. to execute :command:`manage.py compilemessages`) you additionally need:

* `gettext <https://www.gnu.org/software/gettext/>`_.

To build this documentation you need:

* `Python 3.4.x <https://www.python.org/>`_.
* `Sphinx <http://sphinx-doc.org>`_
