.. _intro:

Introduction to Receptor Concepts
=================================

Receptor is meant, primarily, to provide connectivity for services that need
to distribute work across different network topologies

.. image:: ../receptor_arch.png
   :scale: 50%

Nodes connect to each other either by accepting connections from other nodes
or establishing connections to nodes themselves. Once these connections are
established they are treated exactly the same in that they are connection
points for the Receptor mesh network and messages pass over these transport
links to their ultimate destinations regardless of how the connection was
established.

If a connection is lost between two nodes and is considered **stale**, messages
that would normally be routed over that connection will be directed to a more
optimal route. If a more optimal route doesn't exist then messages will be
stored until connectivity is restored to that node, or a new route is created
elsewhere.

NodeID
------

Each **Receptor** node has a *node id* that is used to identify it. This is
separate from any other identifying characteristic (such as hostname or ip
address) since multiple nodes can run on the same host. If the node itself
isn't configured with one then one will be generated for it.

Controllers
-----------



Routers
-------

Executors
---------
