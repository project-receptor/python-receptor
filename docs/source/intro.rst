.. _intro:

Introduction to Receptor
========================

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

Once a message reaches its destination it's handed off to one of the installed
plugins (see :ref:`plugins`) to perform the work. A plugin can send one or more
response messages back to the sender via the mesh until it is finished.

.. image:: basic_receptor.png
    :align: center
    :target: https://github.com/projectreceptor/receptor

.. _concepts:

Terminology and Concepts
------------------------

.. _term_nodes:

Nodes
^^^^^

A **node** is any instance of Receptor running in the mesh, regardless of the role
or purpose it is serving. It is typically connected to other nodes either by
establishing a connection to the other node or receiving a connection.

Nodes broadcast their availability and capabilities to their neighbors on the
mesh. These broadcasts are then relayed to other nodes such that any other node knows
how to route traffic destined for a particular node or group of nodes.

A Node is then capable of routing messages from one node that it knows about to 
other nodes that it knows about. If it is the target of the message, it can perform
the work and send responses back to the sender.

.. _term_controller:

Controllers
^^^^^^^^^^^

A **Controller** is a special type of **Node** in that it is responsible for sending
work to other nodes. Typically a controller is some other system or program
that imports the functionality from the **Receptor** codebase in order to link itself
to the mesh of systems that could act on messages or work needed to be performed by
the system.

There can be one or many controllers present on the mesh. Since controllers are just
another type of node, they can also be capable of performing work or routing messages.

For more details on writing and integrating controllers see :ref:`plugins`

.. _term_work:

Messages, Plugins, and Work
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Receptor mesh itself does not care and is unopinionated about the messages that are
sent across it. Controllers (that send messages and receive responses) and Plugins (that
receive and act on messages) are expected to agree on a contract regarding the format.

The Controller interface has multiple input options for taking data and formatting it into
a message before sending it along to the mesh see :ref:`controller`

Likewise, the plugin interface has multiple options to allow the plugin to inform the mesh
node in how it wants the data delivered to the worker, see :ref:`plugin`

Plugins are just python modules that expose a particular entrypoint. When the Receptor node
starts up it will look for those plugins and import them and include their information
when broadcasting the node's capabilities to its neighbors. All you should need to do to
**install** a plugin is to use **pip** (or yum, dnf, apt, wherever you get your plugins from)

.. _term_flow:

Connections and Message Flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

By default each Node is configured to start a listening service to accept incoming
connections from other nodes. Each node can **also** be configured to reach out and connect
directly to other nodes (called **peers**). This means that each node is likely to have
possibly many connections to other nodes, and this is how the **mesh** is formed.

Once these connections are established it makes NO difference in how and in which direction
messages are routed. The mesh is formed and messages can be routed in any direction and
through any other node.

.. _term_reliability:

Stability, Reliability, and Delivery Consistency
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Receptor makes every effort to deliver messages to the appropriate node, although it makes
no guarantee on the path the message will take through the mesh. If a node along the route
is down or offline then the message will be rerouted through other nodes. If there is no
route available then the message will be stored on the last node that it made it to before
route calculation failed to find another route. The amount of time a message will spend waiting
on the mesh is configurable. If it reaches its timeout an error will be delivered back to the
sender.

A Receptor node itself maintains an internal accounting of messages awaiting delivery but the
mesh itself makes no guarantee that a message **will** be delivered or even ever make it to its
destination. The Controller system should take steps to handle the case where it might not ever
hear back from the mesh about a sent message.