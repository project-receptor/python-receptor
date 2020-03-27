.. _install:

Installing Receptor
===================

Ansible
-------

In the ``/installer`` directory you'll find an Ansible Playbook and Role that will install
Receptor nodes once you provide an ``inventory`` file that looks like this

.. code-block:: yaml

  hostA server_port=32888
  hostB peers=["hostA"]
  hostC peers=["hostB", "hostA:32888"] server_port=8889

This will deploy a 3 node cluster. There are some other ways of tuning the deployment on each node
which you can see by reading the install playbook, run ansible to start the install::

  ansible-playbook -i inventory installer/install.yml

If you would rather deploy manually the installer may still provide a good point of reference
as it contains a template Receptor configuration file at
``installer/roles/receptor_install/templates`` and and a parameterized SystemD unit service
file at ``installer/roles/receptor_install/files``

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
