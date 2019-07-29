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

A **Receptor** Controller exposes an interface on a port that allows other
services to communicate with the Receptor network in order to distribute work
and receive replies.

Routers
-------

**Receptor** Routers manage connections between nodes. Almost all Receptor
nodes are also routers that can participate in directing traffic to where
it needs to go. Even leaf nodes that only have a single connection will
broadcast their availability to perform work out to the larger mesh of
receptors.

Workers
---------

**Receptor** Worker nodes are nodes that have been configured to perform work.
These nodes have plugins installed alongside them that allow them to execute
tasks and respond with status and results. These plugins, when installed,
inform the Receptor network about the node's capabilities and any extra
metadata that may aid the Receptor network in routing work to them. This
information is automatically broadcast to the rest of the Receptor network.
