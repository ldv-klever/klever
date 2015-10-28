Developer documentation
=======================

How to write this documentation
-------------------------------

Please refer to the corresponding subsection of Omega.

Using PyCharm IDE
-----------------

To use PyCharm IDE to develop Psi follow the following steps.

Installation
^^^^^^^^^^^^

Please refer to the corresponding subsection of Omega.

Setting project
^^^^^^^^^^^^^^^

Please refer to the corresponding subsection of Omega.

Configuring the Python interpreter
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Please refer to the corresponding subsection of Omega.

Setting run/debug configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. :menuselection:`Run --> Edit Configurations... --> Add New Configuration`.
#. Select Python from the list.
#. Input *Psi* in field :guilabel:`Name`.
#. Specify :file:`Psi/bin/psi` in field :guilabel:`Script`.
#. Extend existing value of :envvar:`PATH` so that CIF (:file:`cif` or :file:`compiler`) and Aspectator
   (:file:`aspectator`) executables could be found (edit value of field :guilabel:`Environment variables`).
#. Specify working directory somewhere outside the Psi repository (**work_dir**) in field :guilabel:`Working directory`.
#. :menuselection:`OK`.

Creating working directory
^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Run Psi
^^^^^^^

To run Psi press :kbd:`Shift+F10`.

.. note:: If Psi will fatally fail or you will kill Psi, you might need to manually remove
          :file:`psi-work-dir/is solving` in **work_dir** to run Psi fot the next time.

Debug Psi
^^^^^^^^^
To debug Psi press :kbd:`Shift+F9`.

Additional documentation
^^^^^^^^^^^^^^^^^^^^^^^^

A lot of usefull documentation for general using of the PyCharm IDE is available at the official
`PyCharm documentation site <https://www.jetbrains.com/pycharm/documentation/>`_.

