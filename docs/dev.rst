.. Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
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

Developer documentation
=======================

How to write this documentation
-------------------------------

This documentation is created using `Sphinx <http://sphinx-doc.org>`_ from
`reStructuredText <http://docutils.sourceforge.net/rst.html>`_ source files.
To improve existing documentation or to develop the new one you need to read at least the following chapters of the
`Sphinx documentation <http://sphinx-doc.org/contents.html>`_:

#. `Defining document structure <http://sphinx-doc.org/tutorial.html#defining-document-structure>`_.
#. `Adding content <http://sphinx-doc.org/tutorial.html#adding-content>`_.
#. `Running the build <http://sphinx-doc.org/tutorial.html#running-the-build>`_.
#. `reStructuredText Primer <http://sphinx-doc.org/rest.html>`_.
#. `Sphinx Markup Constructs <http://sphinx-doc.org/markup/index.html>`_.
#. `Sphinx Domains <http://sphinx-doc.org/domains.html>`_ (you can omit language specific domains).

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

Using Git repository
--------------------

Klever source code resides in the `Git <https://git-scm.com/>`_ repository.
There is plenty of very good documentation about Git usage.
This section describes just rules specific for the given project.

Update
^^^^^^

#. Periodically synchronize your local repository with the main development repository::

    branch $ git fetch origin
    branch $ git remote prune origin

   .. note:: This is especially required when you are going to create a new branch or to merge some branch to the master
             branch.

#. Pull changes if so::

    branch $ git pull --rebase origin branch

   .. warning:: Forget about pulling without rebasing!

#. Resolve conflicts if so.

Fixing bugs and implementing new features
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. One must create a new branch to fix each individual bug or implement a new feature::

    master $ git checkout -b fix-conf

   .. warning:: Do not intermix fixes and implementation of completely different bugs and features into one branch.
                Otherwise other developers will need to wait or to make some tricky things like cherry-picking and
                merging of non-master branches.
                Eventually this can lead to very unpleasant consequences, e.g. the master branch can be broken because
                of one will suddenly add bad code their by merging his/her branch based on another non working branch.

#. Push all new branches to the main development repository.
   As well re-push them at least one time a day if you make some commits::

    fix-conf $ git push origin fix-conf

#. Merge the master branch into your new branches if you need some recent bug fixes or features::

    fix-conf $ git merge master

   .. note:: Do not forget to update the master branch from the main development repository.

   .. note:: Do not merge remote-tracking branches.

#. Ask Evgeny Novikov or/and Ilja Zakharov (novikov@ispras.ru) to review and to merge branches to the master branch when
   corresponding bugs/features are fixed/implemented.

#. Delete merged branches locally and remotely::

    master $ git branch -d fix-conf
    master $ git push origin :fix-conf

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

Using PyCharm IDE
-----------------

To use PyCharm IDE to develop Klever follow the following steps.

Installation
^^^^^^^^^^^^

#. Download PyCharm Professional from `<https://www.jetbrains.com/pycharm/download/>`_ (below all settings are given
   for version 2017.1.1, you have to adapt them for your version by yourself).
#. Follow installation instructions provided at that site.
#. Activate the PyCharm license using your JetBrains account (request for the license from Evgeny Novikov
   novikov@ispras.ru).
#. Specify your preferences at the "Welcome to PyCharm" window.

Setting project
^^^^^^^^^^^^^^^

At the "Welcome to PyCharm" window:

#. :menuselection:`Open`.
#. Specify the absolute path to directory :file:`bridge` from the root directory of the main development repository.
#. :menuselection:`OK`.

Configuring the Python interpreter
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. :menuselection:`File --> Settings --> Project: Bridge --> Project Interpreter --> Settings --> More..`.
#. Select Python 3.4 or higher from the list and press :kbd:`Enter`.
#. Input *Python 3* in field :guilabel:`name`.
#. :menuselection:`OK`.
#. Ditto for *core*, *docs* and *scheduler*.

Setting run/debug configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Common run/debug configurations are included into the Klever project.
Common configurations with names starting with **$** should be copied to configurations with names without **$** and
adjusted in accordance with instructions below.
If you want to adjust configurations with names that not starting with **$** you also have to copy them before.

#. :menuselection:`Run --> Edit Configurations...`.

Klever Bridge run/debug configuration
"""""""""""""""""""""""""""""""""""""

* Specify *0.0.0.0* in field :guilabel:`Host` if you want to share your Klever Bridge to the local network.
* Specify your preferred port in field :guilabel:`Port`.

.. note:: To make your Klever Bridge accessible from the local network you might need to set up your firewall
          accordingly.

Klever Core run/debug configuration
"""""""""""""""""""""""""""""""""""

This run/debug configuration is only useful if you are going to debug Klever Core.

* Extend existing value of environment variable :envvar:`PATH` so that CIF (:file:`cif` or :file:`compiler`),
  Aspectator (:file:`aspectator`) and CIL (:file:`cilly.asm.exe`) binaries could be found (edit value of field
  :guilabel:`Environment variables`).
* Specify the absolute path to the working directory in field :guilabel:`Working directory`.

   .. note:: Place Klever Core working directory somewhere outside the main development repository.

   .. note:: Klever Core will search for its configuration file :file:`core.json` in the specified working directory.
             Besides you can provide this file by passing its name as a first parameter to the script.

Documentation run/debug configuration
"""""""""""""""""""""""""""""""""""""

Specify another representation of documenation in field :guilabel:`Command` if you need it.

Testing
^^^^^^^

Klever Bridge testing
"""""""""""""""""""""

#. :menuselection:`Tools --> Run manage.py Task...`::

    manage.py@bridge > test

.. note:: To start tests from console::

    $ cd bridge
    $ python3 manage.py test

.. note:: Another way to start tests from console::

    $ python3 path/to/klever/bridge/manage.py test bridge users jobs reports marks service

.. note:: The test database is created and deleted automatically. If the user will interrupt tests the test database
          will preserved and the user will be asked for its deletion for following testing. 

.. note:: PyCharm has reach abilities to analyse tests and their results. 

Additional documentation
^^^^^^^^^^^^^^^^^^^^^^^^

A lot of usefull documentation for developing Django projects as well as for general using of the PyCharm IDE is
available at the official `PyCharm documentation site <https://www.jetbrains.com/pycharm/documentation/>`_.

..
    TODO
    ----

    The rest should be totally revised!

    Creating Klever Core working directory
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    Create **work_dir**.

    Specifying Klever Core configuration
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    #. Copy Klever Core configuration file :file:`core/core.json` to **work_dir**.
    #. Edit the copied file:
        * Specify the identifier of the job you are going to solve (the value of property *identifier*).
        * Specify the name of Klever Bridge and your credentials (values of properties *Klever Bridge.name*,
          *Klever Bridge.user* and *Klever Bridge.password* correspondingly).
          The specified Klever Bridge user should have service rights.
        * Switch values of properties *debug* and *allow local source directories use* to *true*.

    Fetching Linux kernel source code
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    Get somehow source code of some version of the Linux kernel and place it to **work_dir**.

    .. note:: The value of property *Linux kernel.src* of the specified job configuration should be the name of the
              directory where you will place Linux kernel source code.

    Run
    ^^^

    To run press :kbd:`Shift+F10`.

    .. note:: If Klever Core will fatally fail or you will hardly kill Klever Core, you might need to manually remove file
              :file:`is solving` inside **work_dir** to run Klever Core fot the next time.

    Debug
    ^^^^^

    To debug press :kbd:`Shift+F9`.

    Run Klever Bridge manage.py tasks
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    To run manage.py tasks:

    #. :menuselection:`Tools --> Run manage.py Task...`.
    #. Some manage.py tasks are described in the :ref:`klever-bridge-install` section.

    Run cloud tools in PyCharm
    ^^^^^^^^^^^^^^^^^^^^^^^^^^

    To be able to solve tasks on your machine you need to run Klever client-controller and native scheduler tools. Follow
    the steps:

    #. First install all requirements and prepare configuration properties according to the installation documentation.
       Do it after you have working Klever Bridge server.
       All additional tools and configuration files should be outside from the Klever sources and corresponding working
       directories.

    #. Run client-controller. Use script :file:`Scheduler/bin/client-controller.py` and path to a prepared client-controller
       configuration file as the first argument. Be sure that you have chosen clean working directory outside of sources
       for an execution. If you would turn on web-UI in configuration and place necessary files in the consul
       directory you will get a visualization of all checks at *http://localhost:8500/ui*.

    #. Run native scheduler after you have running controller and Klever Bridge server. Run script
       :file:`Scheduler/bin/native-scheduler.py` with the path to a scheduler configuration file as a single argument. Be sure
       that you have chosen clean working directory outside of sources for an execution.

       .. note:: At least on openSUSE 13.2 it's required to specify :envvar:`JAVA` to run CPAchecker, e.g.
              :file:`/usr/lib64/jvm/java-1.7.0-openjdk/jre/bin/java`.

    #. TODO: not only this command but 3 more! Moreover this should be placed somewhere else as well as all run instructions.
       Before running any tasks be sure that you have properly configured machine with swap accounting (or better disable
       swap runnning *sudo swapoff -a*) and available cgroup subsystems (it is often necessary to run
       *sudo chmod o+wt '/sys/fs/cgroup/cpuset/'*).

    #. Check out at client-controller consul web-UI that all checks are passing now. The address by defauilt is
       `localhost:8500 <http://localhost:8500/ui>`_.
