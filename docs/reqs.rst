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

Klever Bridge
-------------

To run Klever Bridge you need:

* `Python 3.4 or higher <https://www.python.org/>`_ and its packages:

  * `Django <https://www.djangoproject.com/>`__.
  * `pytz <http://pythonhosted.org/pytz/>`__.

    .. note:: The corresponding openSUSE RPM package is likely broken since it couldn't be updated properly.
              Please, uninstall it and install the latest version of *pytz*.

  * `mysqlclient <https://github.com/PyMySQL/mysqlclient-python>`__ (requires Python and MySQL development headers and
    libraries) or `psycopg2 <https://pypi.python.org/pypi/psycopg2>`__ (requires
    `libpq <https://www.postgresql.org/docs/current/static/libpq.html>`__).

* `MySQL <https://www.mysql.com/>`__/`MariaDB <https://mariadb.org/>`__ or `PostgreSQL <https://www.postgresql.org/>`__
  (server).

To run a production server you additionally need `apache2 <http://httpd.apache.org/>`__ and its module
`mod_wsgi <https://code.google.com/p/modwsgi/>`__ or `NGINX <https://www.nginx.com/>`__ and Python package
`Gunicorn <https://pypi.python.org/pypi/gunicorn>`__.

To translate Klever Bridge (i.e. to execute :command:`manage.py compilemessages`) you additionally need
`gettext <https://www.gnu.org/software/gettext/>`__.

Klever Core
-----------

To run Klever Core you need:

* `Python 3.4 or higher`_ and its packages:

  * `Jinja2 <http://jinja.pocoo.org/>`__ (just if you are going to verify source code against rule specifications using
    argument signatures).
  * `ply <https://pypi.python.org/pypi/ply>`__.
  * `graphviz <https://pypi.python.org/pypi/graphviz>`__.
  * `requests <https://pypi.python.org/pypi/requests/>`__.
  * `setuptools_scm <https://pypi.python.org/pypi/setuptools_scm/>`__.
  * `pympler <https://pypi.python.org/pypi/Pympler>`__.

* `GNU make <https://www.gnu.org/software/make/>`__.
* `GNU bc <https://www.gnu.org/software/bc/>`__.
* `git <https://git-scm.com/>`__ (just if you are going to verify commits to Git repositories).
* `graphviz <http://graphviz.org/>`__.
* `CIF <http://forge.ispras.ru/projects/cif>`__.

TODO: Klever Scheduler
----------------------

If you are going to execute on your machine scheduler or the other Klever Cloud tools you need:

* `Python 3.4 or higher`_ and its packages:

  * `consulate <https://pypi.python.org/pypi/consulate>`__.
  * `requests <https://pypi.python.org/pypi/requests/>`__.

* `GNU bc <https://www.gnu.org/software/bc/>`__.
* `BenchExec <http://github.com/dbeyer/benchexec>`__.
* `Consul binaries and optionally UI <http://www.consul.io/downloads.html>`__. Download binary file and UI-files
  directory and place them nearby in a an arbitrary directory. Building or installation are not required.
