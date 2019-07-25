.. Receptor documentation master file, created by
   sphinx-quickstart on Mon Jul  1 00:30:50 2019.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Receptor
========

Project Receptor is a flexible multi-service relayer with remote execution and
orchestration capabilities linking controllers with executors across a mesh of
nodes. It's intended to be used on any type of network topology across data
centers and clouds, especially when passing between zones that might have
different ingress patterns and security policies.

Receptor connects services that have work to do with other nodes that can
perform the work, typically because that work needs to be done closer to the
target of the work which might not be directly accessible to the systems
producing the work.

There are 3 major components to a Receptor network, any node can act as one of
these components

* Controller: Accepts work from an external system in order to be delivered to
  the Receptor network
* Router: Routes work between nodes. It starts a server in order for nodes to
  connect directly to it, it also makes direct connection to peers. These
  connections work the same and messages can be passed over them in any
  direction to other nodes as needed.
* Worker: Uses plugins that match the message type, the payload is delivered to
  the execution plugin and any output is delivered back into the Receptor
  network.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   intro
   install
   interface
   plugins


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
