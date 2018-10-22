.. Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
   Ivannikov Institute for System Programming of the Russian Academy of Sciences
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

Developer Documentation
=======================

How to Write This Documentation
-------------------------------

This documentation is created using `Sphinx <http://sphinx-doc.org>`__ from
`reStructuredText <http://docutils.sourceforge.net/rst.html>`__ source files.
To improve existing documentation or to develop the new one you need to read at least the following chapters of the
`Sphinx documentation <http://sphinx-doc.org/contents.html>`__:

#. `Defining document structure <http://sphinx-doc.org/tutorial.html#defining-document-structure>`__.
#. `Adding content <http://sphinx-doc.org/tutorial.html#adding-content>`__.
#. `Running the build <http://sphinx-doc.org/tutorial.html#running-the-build>`__.
#. `reStructuredText Primer <http://sphinx-doc.org/rest.html>`__.
#. `Sphinx Markup Constructs <http://sphinx-doc.org/markup/index.html>`__.
#. `Sphinx Domains <http://sphinx-doc.org/domains.html>`__ (you can omit language specific domains).

Please, follow these advises:

#. Do not think that other developers and especially users are so smart as you are.
#. Clarify ambiguous things and describe all the details without missing anything.
#. Avoid and fix misprints.
#. Write each sentence on a separate line.
#. Do not use blank lines except it is required.
#. Write a new line at the end of each source file.
#. Break sentences longer than 120 symbols to several lines if possible.

To develop documentation it is recommended to use some visual editor.

.. warning:: Please do not reinvent the wheel!
   If you are a newbie then examine carefully the existing documentation and create the new one on that basis.
   Just if you are a guru then you can suggest to improve the existing documentation.

Using Git Repository
--------------------

Klever source code resides in the `Git <https://git-scm.com/>`__ repository.
There is plenty of very good documentation about Git usage.
This section describes just rules specific for the given project.

Update
^^^^^^

#. Periodically synchronize your local repository with the main development repository (it is available just internally
   at ISP RAS)::

    branch $ git fetch origin
    branch $ git remote prune origin

   .. note:: This is especially required when you are going to create a new branch or to merge some branch to the master
             branch.

#. Pull changes if so::

    branch $ git pull --rebase origin branch

   .. warning:: Forget about pulling without rebasing!

#. Resolve conflicts if so.

Fixing Bugs and Implementing New Features
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. One must create a new branch to fix each individual bug or implement a new feature::

    master $ git checkout -b fix-conf

   .. warning:: Do not intermix fixes and implementation of completely different bugs and features into one branch.
                Otherwise other developers will need to wait or to make some tricky things like cherry-picking and
                merging of non-master branches.
                Eventually this can lead to very unpleasant consequences, e.g. the master branch can be broken because
                of one will merge there a branch based on another non working branch.

#. Push all new branches to the main development repository.
   As well re-push them at least one time a day if you make some commits::

    fix-conf $ git push origin fix-conf

#. Merge the master branch into your new branches if you need some recent bug fixes or features::

    fix-conf $ git merge master

   .. note:: Do not forget to update the master branch from the main development repository.

   .. note:: Do not merge remote-tracking branches.

#. Ask senior developers to review and to merge branches to the master branch when corresponding bugs/features are
   fixed/implemented.

#. Delete merged branches::

    master $ git branch -d fix-conf

Releases
--------

Generally we follow the same rules as for development of the Linux kernel.

Each several months a new release will be issued, e.g. 0.1, 0.2, 1.0.

Just after this a merge window of several weeks will be opened.
During the merge window features implemented after a previous merge window or during the given one will be merged to
master.

After the merge window just bug fixes can be merged to the master branch.
During this period we can issue several release candidates, e.g. 1.0-rc1, 1.0-rc2.

In addition, after issuing a new release we can decide to support a stable branch.
This branch will start from a commit corresponding to the given release.
It can contain just bug fixes relevant to an existing functionality and not to a new one which is supported within a
corresponding merge window.

.. _dev_deploy:

Deployment for Development Purposes
-----------------------------------

To deploy Klever for development purposes in addition to using mode *development* (see :ref:`local_deploy`) one needs
to specify command-line option *--allow-symbolic-links*.

Using PyCharm IDE
-----------------

To use PyCharm IDE for developing Klever follow the following steps.

Installation
^^^^^^^^^^^^

#. Download PyCharm Community from `<https://www.jetbrains.com/pycharm/download/>`_ (below all settings are given for
   version 2017.1.1, you have to adapt them for your version by yourself).
#. Follow installation instructions provided at that site.

Setting Project
^^^^^^^^^^^^^^^

At the "Welcome to PyCharm" window:

#. Specify your preferences.
#. :menuselection:`Open`.
#. Specify the absolute path to directory :file:`$KLEVER_SRC/bridge`.
#. :menuselection:`OK`.

Configuring the Python Interpreter
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. :menuselection:`File --> Settings --> Project: Bridge --> Project Interpreter --> Settings --> More..`.
#. Select Python 3.4 or higher from the list and press :kbd:`Enter`.
#. Input *Python 3* in field :guilabel:`name`.
#. :menuselection:`OK`.
#. Ditto for *core*, *deploys*, *docs*, *scheduler* and *utils*.

Setting Run/Debug Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Common run/debug configurations are included into the Klever project.
Common configurations with names starting with **$** should be copied to configurations with names without **$** and
adjusted in accordance with instructions below.
If you want to adjust configurations with names that not starting with **$** you also have to copy them before.

#. :menuselection:`Run --> Edit Configurations...`.

Klever Bridge Run/Debug Configuration
"""""""""""""""""""""""""""""""""""""

.. note:: This is available just for PyCharm Professional.

* Specify *0.0.0.0* in field :guilabel:`Host` if you want to share your Klever Bridge to the local network.
* Specify your preferred port in field :guilabel:`Port`.

.. note:: To make your Klever Bridge accessible from the local network you might need to set up your firewall
          accordingly.

Klever Core Run/Debug Configuration
"""""""""""""""""""""""""""""""""""

This run/debug configuration is only useful if you are going to debug Klever Core.

* Extend existing value of environment variable :envvar:`PATH` so that CIF (:file:`cif` or :file:`compiler`),
  Aspectator (:file:`aspectator`) and CIL (:file:`cilly.asm.exe`) binaries could be found (edit value of field
  :guilabel:`Environment variables`).
* Specify the absolute path to the working directory in field :guilabel:`Working directory`.

   .. note:: Place Klever Core working directory somewhere outside the main development repository.

   .. note:: Klever Core will search for its configuration file :file:`core.json` in the specified working directory.
             Thus, the best workflow to debug Klever Core is to set its working directory to the one created previously
             when it was run without debugging.
             Besides, you can provide this file by passing its name as a first parameter to the script.

Documentation Run/Debug Configuration
"""""""""""""""""""""""""""""""""""""

Specify another representation of documenation in field :guilabel:`Command` if you need it.

Testing
^^^^^^^

Klever Bridge Testing
"""""""""""""""""""""

.. note:: This is available just for PyCharm Professional.

#. :menuselection:`Tools --> Run manage.py Task...`::

    manage.py@bridge > test

.. note:: To start tests from console::

    $ cd bridge
    $ python3 manage.py test

.. note:: Another way to start tests from console::

    $ python3 path/to/klever/bridge/manage.py test bridge users jobs reports marks service

.. note:: The test database is created and deleted automatically.
          If the user will interrupt tests the test database will preserved and the user will be asked for its deletion
          for following testing.
          The user should be allowed to create databases (using command-line option *--keedb* does not help).

.. note:: PyCharm has reach abilities to analyse tests and their results. 

Additional documentation
^^^^^^^^^^^^^^^^^^^^^^^^

A lot of usefull documentation for developing Django projects as well as for general using of the PyCharm IDE is
available at the official `site <https://www.jetbrains.com/pycharm/documentation/>`__.
