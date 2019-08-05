.. _install:

Installing Receptor
===================

**Receptor** is provided from several different locations depending on how you
want to use it.

Using pip
---------

Python 3.6+ is required::

  $ pip install receptor


From source
-----------

Check out the source code from `github <https://github.com/project-receptor/receptor>`_::

  $ git clone git://github.com/project-receptor/receptor

Then install::

  $ python setup.py install

OR::

  $ pip install .

.. _builddist:

Building the distribution
-------------------------

To produce an installable ``wheel`` file::

  make dist

To produce a distribution tarball::

  make sdist

.. _buildcontimg:

Building the base container image
---------------------------------

TODO

Building the RPM
----------------

TODO
