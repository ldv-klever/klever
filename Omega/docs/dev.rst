Developer documentation
=======================

How to write this documentation
-------------------------------

The Omega documentation is created using `Sphinx <http://sphinx-doc.org>`_ from
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

To use PyCharm IDE to develop Omega follow the following steps.

Installation
^^^^^^^^^^^^

#. Download the PyCharm Professional Edition 4.5.x from `<https://www.jetbrains.com/pycharm/download/>`_ (other versions
   weren't tested, below all settings are given for version 4.5.3).
#. Follow installation instructions provided at that site.
#. Activate the PyCharm license.
#. Specify your preferences until the "Welcome to PyCharm" window.

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
#. Select *Django server* from the list.
#. Input *Omega* in field :guilabel:`Name`.
#. Specify *0.0.0.0* in field :guilabel:`Host` if you want to share your Omega in the local network.
#. Specify *8998* in field :guilabel:`Port`.
#. :menuselection:`OK`.

.. note:: To make your Omega accessible from the local network you might need to set up your firewall accordingly.

Run development server
^^^^^^^^^^^^^^^^^^^^^^

To run the development server press :kbd:`Shift+F10`.

Debug development server
^^^^^^^^^^^^^^^^^^^^^^^^

To debug the development server press :kbd:`Shift+F9`.

Run manage.py tasks
^^^^^^^^^^^^^^^^^^^

To run manage.py tasks:
#. :menuselection:`Tools --> Run manage.py Task...`.
#. Some manage.py tasks are described in the :ref:`install` section.

Additional documentation
^^^^^^^^^^^^^^^^^^^^^^^^

A lot of usefull documentation for developing Django projects as well as for general using of the PyCharm IDE is
available at the official `PyCharm documentation site <https://www.jetbrains.com/pycharm/documentation/>`_.

