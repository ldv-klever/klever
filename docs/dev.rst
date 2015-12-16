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

   .. note:: Trivial bugs/features can be fixed/implemented directly in the master branch.
             Most likely you will not have any conflict but you will save some time.

#. Push all new branches to the main development repository.
   As well re-push them at least one time a day if you make some commits::

    fix-conf $ git push origin fix-conf

#. Merge the master branch into your new branches if you need some recent bug fixes or features::

    fix-conf $ git merge master

   .. note:: Do not forget to update the master branch from the main development repository.

   .. note:: Do not merge remote-tracking branches.

#. Merge branches to the master branch when corresponding bugs/features are fixed/implemented::

    fix-conf $ git checkout master
    master $ git merge fix-conf

   .. note:: Do not forget to update the master branch from the main development repository before merging.

#. Push the master branch to the main development repository::

    master $ git push origin master

#. Delete merged branches locally and remotely::

    master $ git branch -d fix-conf
    master $ git push origin :fix-conf

Using PyCharm IDE
-----------------

To use PyCharm IDE to develop Klever follow the following steps.

Installation
^^^^^^^^^^^^

#. Download the PyCharm Professional Edition 4.5.x from `<https://www.jetbrains.com/pycharm/download/>`_ (other versions
   weren't tested, below all settings are given for version 4.5.3).
#. Follow installation instructions provided at that site.
#. Activate the PyCharm license.
#. Specify your preferences at the "Welcome to PyCharm" window.

.. note:: At least on openSUSE 13.2 to run PyCharm one needs to specify :envvar:`JDK_HOME`, e.g.
          :file:`/usr/lib64/jvm/java-1.8.0-openjdk-1.8.0/jre/`.

Setting project
^^^^^^^^^^^^^^^

At the "Welcome to PyCharm" window:

#. :menuselection:`Open`.
#. Specify :file:`Bridge`.
#. :menuselection:`OK`.

Configuring the Python interpreter
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. :menuselection:`File --> Settings --> Project: Bridge --> Project Interpreter --> Settings --> More..`.
#. Select Python 3.4.x from the list and press :kbd:`Enter`.
#. Input *Python 3.4* in field :guilabel:`name`.
#. :menuselection:`OK`.
#. Ditto for *Core*, *Scheduler* and *docs*.

Setting run/debug configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. :menuselection:`Run --> Edit Configurations... --> Add New Configuration`.

Klever Bridge run/debug configuration
"""""""""""""""""""""""""""""""""""""

#. Select :menuselection:`Django server`.
#. Input *Bridge* in field :guilabel:`Name`.
#. Specify *0.0.0.0* in field :guilabel:`Host` if you want to share your Klever Bridge in the local network.
#. Specify *8998* in field :guilabel:`Port`.
#. :menuselection:`OK`.

.. note:: To make your Klever Bridge accessible from the local network you might need to set up your firewall accordingly.

Klever Core run/debug configuration
"""""""""""""""""""""""""""""""""""

#. Select :menuselection:`Python`.
#. Input *Core* in field :guilabel:`Name`.
#. Specify :file:`Core/bin/klever-core` in field :guilabel:`Script`.
#. Select project *Core* in field :guilabel:`Project`.
#. Extend existing value of :envvar:`PATH` so that CIF (:file:`cif` or :file:`compiler`) and Aspectator
   (:file:`aspectator`) executables could be found (edit value of field :guilabel:`Environment variables`).
#. Specify working directory somewhere outside the repository (**work_dir**) in field :guilabel:`Working directory`.
#. :menuselection:`OK`.


Documentation run/debug configuration
"""""""""""""""""""""""""""""""""""""

#. Select :menuselection:`Python docs --> Sphinx task`.
#. Input *docs* in field :guilabel:`Name`.
#. Specify :file:`docs` in field :guilabel:`Input`.
#. Specify :file:`docs/_build/html` in field :guilabel:`Output`.
#. Select project *docs* in field :guilabel:`Project`.
#. :menuselection:`OK`.

Creating Klever Core working directory
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Create **work_dir**.

Specifying Klever Core configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Copy :file:`Core/klever core conf.json` to **work_dir**.
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

.. note:: If Klever Core will fatally fail or you will hardly kill Klever Core, you might need to manually remove
          :file:`is solving` inside **work_dir** to run Klever Core fot the next time.

Debug
^^^^^

To debug press :kbd:`Shift+F9`.

Run Klever Bridge manage.py tasks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To run manage.py tasks:

#. :menuselection:`Tools --> Run manage.py Task...`.
#. Some manage.py tasks are described in the :ref:`klever-bridge-install` section.

Additional documentation
^^^^^^^^^^^^^^^^^^^^^^^^

A lot of usefull documentation for developing Django projects as well as for general using of the PyCharm IDE is
available at the official `PyCharm documentation site <https://www.jetbrains.com/pycharm/documentation/>`_.

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
