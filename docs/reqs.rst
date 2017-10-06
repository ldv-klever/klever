.. Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
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

Requirements
============

Documentation
-------------

To build this documentation you need:

* `Python 3.4 or higher <https://www.python.org/>`_.
* `Sphinx <http://sphinx-doc.org>`_

Klever Bridge
-------------

To run Klever Bridge you need:

* `Python 3.4 or higher <https://www.python.org/>`_ and its packages:

  * `Django <https://www.djangoproject.com/>`_.
  * `pytz <http://pythonhosted.org/pytz/>`_.

    .. note:: The corresponding openSUSE RPM package is likely broken since it couldn't be updated properly.
              Please, uninstall it and install the latest version of *pytz*.

  * `mysqlclient <https://github.com/PyMySQL/mysqlclient-python>`_ (requires Python and MySQL development headers and
    libraries) or `psycopg2 <https://pypi.python.org/pypi/psycopg2>`_ (requires
    `libpq <https://www.postgresql.org/docs/current/static/libpq.html>`_).

* `MySQL <https://www.mysql.com/>`_/`MariaDB <https://mariadb.org/>`_ or `PostgreSQL <https://www.postgresql.org/>`_
  (server).

To run a production server you additionally need `apache2 <http://httpd.apache.org/>`_ and its module
`mod_wsgi <https://code.google.com/p/modwsgi/>`_ or `NGINX <https://www.nginx.com/>`_ and Python package
`Gunicorn <https://pypi.python.org/pypi/gunicorn>`_.

To translate Klever Bridge (i.e. to execute :command:`manage.py compilemessages`) you additionally need
`gettext <https://www.gnu.org/software/gettext/>`_.

Klever Core
-----------

To run Klever Core you need:

* `Python 3.4 or higher <https://www.python.org/>`_ and its packages:

  * `Jinja2 <http://jinja.pocoo.org/>`_ (just if you are going to verify source code against rule specifications using
    argument signatures).
  * `ply <https://pypi.python.org/pypi/ply>`_.
  * `graphviz <https://pypi.python.org/pypi/graphviz>`_.
  * `requests <https://pypi.python.org/pypi/requests/>`_.
  * `setuptools_scm <https://pypi.python.org/pypi/setuptools_scm/>`_.
  * `pympler <https://pypi.python.org/pypi/Pympler>`_.

* `GNU make <https://www.gnu.org/software/make/>`_.
* `GNU bc <https://www.gnu.org/software/bc/>`_.
* `git <https://git-scm.com/>`_ (just if you are going to verify commits to Git repositories).
* `graphviz <http://graphviz.org/>`_.
* `CIF <http://forge.ispras.ru/projects/cif>`_.

TODO: Klever Scheduler
----------------------

If you are going to execute on your machine scheduler or the other Klever Cloud tools you need:

* `Python 3.4 or higher <https://www.python.org/>`_ and its packages:

  * `consulate <https://pypi.python.org/pypi/consulate>`_.
  * `requests <https://pypi.python.org/pypi/requests/>`_.

* `GNU bc <https://www.gnu.org/software/bc/>`_.
* `BenchExec sources <http://github.com/dbeyer/benchexec>`_.
* `Consul binaries and optionally UI <http://www.consul.io/downloads.html>`_. Download binary file and UI-files
  directory and place them nearby in a an arbitrary directory. Building or installation are not required.
