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

.. note:: At least on openSUSE 13.2 it's required to specify :envvar:`JDK_HOME`, e.g.
          :file:`/usr/lib64/jvm/java-1.8.0-openjdk-1.8.0/jre/`.

Setting project
^^^^^^^^^^^^^^^

At the "Welcome to PyCharm" window:

#. :menuselection:`Open`.
#. Specify the path to :file:`Omega`.
#. :menuselection:`OK`.

Configuring the Python interpreter
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. :menuselection:`File --> Settings --> Project: Omega --> Project Interpreter --> Settings --> More..`.
#. Select Python 3.4.x from the list and press :kbd:`Enter`.
#. Input *Python 3.4* in field :guilabel:`name`.
#. :menuselection:`OK`.

Setting run/debug configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. :menuselection:`Run --> Edit Configurations... --> Add New Configuration`.

Omega run/debug configuration
"""""""""""""""""""""""""""""

#. Select :menuselection:`Django server`.
#. Input *Omega* in field :guilabel:`Name`.
#. Specify *0.0.0.0* in field :guilabel:`Host` if you want to share your Omega in the local network.
#. Specify *8998* in field :guilabel:`Port`.
#. :menuselection:`OK`.

.. note:: To make your Omega accessible from the local network you might need to set up your firewall accordingly.

Psi run/debug configuration
"""""""""""""""""""""""""""

#. Select :menuselection:`Python`.
#. Input *Psi* in field :guilabel:`Name`.
#. Specify :file:`Psi/bin/psi` in field :guilabel:`Script`.
#. Extend existing value of :envvar:`PATH` so that CIF (:file:`cif` or :file:`compiler`) and Aspectator
   (:file:`aspectator`) executables could be found (edit value of field :guilabel:`Environment variables`).
#. Specify working directory somewhere outside the Psi repository (**work_dir**) in field :guilabel:`Working directory`.
#. Select project *Psi* in field :guilabel:`Project`.
#. :menuselection:`OK`.


Documentation run/debug configuration
"""""""""""""""""""""""""""""""""""""

#. Select :menuselection:`Python docs --> Sphinx task`.
#. Input *docs* in field :guilabel:`Name`.
#. Specify :file:`docs` in field :guilabel:`Input`.
#. Specify :file:`docs/_build` in field :guilabel:`Output`.
#. Select project *docs* in field :guilabel:`Project`.
#. :menuselection:`OK`.

Creating Psi working directory
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Create **work_dir**.

Specifying Psi configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. Copy :file:`Psi/psi-conf.json` to **work_dir**.
#. Edit the copied file:
    * Specify the identifier of the job you are going to solve (the value of property *job.id*).
    * Specify the name of Omega and your credentials (values of properties *Omega.name*, *Omega.user* and *Omega.passwd*
      correspondingly).
      If the value of *Omega.user* will be left *"null"* your OS user name will be used.
      If the value of *Omega.passwd* will be left *"null"* you will be asked to secretly enter your password when you
      will run Psi.
      The specified Omega user should have Operator rights for the specified job.
    * Switch value of property *allow local source directories use* to *true*.

Fetching Linux kernel source code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Get somehow source code of some version of the Linux kernel and place it to **work_dir**.

.. note:: The value of property *Linux kernel.src* of the specified job configuration should be the name of the
          directory where you will place Linux kernel source code.

Run
^^^

To run press :kbd:`Shift+F10`.

.. note:: If Psi will fatally fail or you will kill Psi, you might need to manually remove :file:`is solving` inside
          **work_dir** to run Psi fot the next time.

Debug
^^^^^

To debug press :kbd:`Shift+F9`.

Run Omega manage.py tasks
^^^^^^^^^^^^^^^^^^^^^^^^^

To run manage.py tasks:

#. :menuselection:`Tools --> Run manage.py Task...`.
#. Some manage.py tasks are described in the :ref:`omega-install` section.

Additional documentation
^^^^^^^^^^^^^^^^^^^^^^^^

A lot of usefull documentation for developing Django projects as well as for general using of the PyCharm IDE is
available at the official `PyCharm documentation site <https://www.jetbrains.com/pycharm/documentation/>`_.

Run cloud tools in PyCharm
^^^^^^^^^^^^^^^^^^^^^^^^^^

To be able to solve tasks on your machine you need to run Klever client-controller and native scheduler tools. Follow
the steps:

#. First install all requirements and prepare configuration properties according to the installation documentation.
   Do it after you have working Omega server.

#. Run client-controller. Use script :file:`Cloud/bin/client-controller` and prepared client-controller configuration
   file as the first argument. If you would turn on web-UI in configuration and place necessary files in the consul
   directory you will get a visualization of all checks at *http://localhost:8500/ui*.

#. Run native scheduler after you have running controller and Omega server. Run script :file:`Cloud/bin/scheduler` with
   the scheduler configuration file as a single argument.

#. Check out at client-controller consul web-UI that all checks are passing now.
