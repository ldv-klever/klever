Requirements
============

Documentation
-------------

To build this documentation you need:

* `Python 3.4.x <https://www.python.org/>`_.
* `Sphinx <http://sphinx-doc.org>`_

Omega
-----

To run Omega you need:

* `Python 3.4.x <https://www.python.org/>`_ and its packages:

  * `Django <https://www.djangoproject.com/>`_.
  * `pytz <http://pythonhosted.org/pytz/>`_.
  * `mysqlclient <https://github.com/PyMySQL/mysqlclient-python>`_ (requires Python and MySQL development headers and
    libraries).

* `MySQL <https://www.mysql.com/>`_/`MariaDB <https://mariadb.org/>`_ (server).

To run a production server you additionally need `apache2 <http://httpd.apache.org/>`_ and its module
`mod_wsgi <https://code.google.com/p/modwsgi/>`_.

To translate Omega (i.e. to execute :command:`manage.py compilemessages`) you additionally need
`gettext <https://www.gnu.org/software/gettext/>`_.

Cloud
-----

If you are going to execute on your machine scheduler or the other Klever Cloud tools you need:

* `Python 3.4.x <https://www.python.org/>`_ and its packages:

  * `consulate <https://pypi.python.org/pypi/consulate>`_.
  * `requests <https://pypi.python.org/pypi/requests/>`_.

* `BenchExec sources <http://github.com/dbeyer/benchexec>`_.
* `Consul binaries and optionally UI <http://www.consul.io/downloads.html>`_. Web-interface is expected in the consul
root directory.