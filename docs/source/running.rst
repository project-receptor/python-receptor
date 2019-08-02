.. _running:

Configuring Receptor
====================

Receptor nodes need to be configured to work together in order to be useful.
There isn't currently a mechanism for auto-discovery of Receptor nodes so it's
important to consider how nodes themselves will be configured to talk to one
another.

Each **Receptor** node can run a server that accepts connections from other
nodes. Simultaneously Receptor can be configured to connect directly to other
nodes. Once these connections are established they are treated the same way
with the exception that connections established by the node itself will attempt
to reestablish a connection that is lost.

Example Controller Configuration File::

  [server]
  port=8888             # Port to bind listening service to
  address=0.0.0.0       # Interface to bind listening service to
  server_disable=False  # Should the listening service be disabled?
  debug=False           # Much verbose logging!
  ssl_certificate=/path # Path to the certificate chain
  ssl_key=/path         # Path to the ssl key
  socket_path=/path     # Path to the controller message socket

  [receptor]
  node_id=someident     # The identifier for this receptor node

  [peers]
  hostname:8889         # Remote address including port for a...
  a.b.c.d:8888          # ...receptor node to connect to and peer with

 
``port`` and ``address``
-------------------------

 When ``server_disable`` is ``False`` and the server is enabled, the Receptor
 node will accept connections from other nodes on this interface and port.

 
``server_disable``
------------------

This disables the incoming connection server entirely. Typically you would use
this if you only intended this nodes to establish connections to other nodes.

``debug``
---------

Turns on extra verbose logging.

``ssl_certificate`` and ``ssl_key``
-----------------------------------

This adds the certificate chain and key and enables TLS for all connections.

``socket_path``
---------------

This is used by **Receptor** when it's launched as a **Controller**. This is
the local unix socket path interface that other systems will use to send work to
the Receptor network.

``peers``
---------

This is a list of addresses to connect to. There's no functional difference
between these peers and nodes that connect to the server that your Receptor node
is running.

If the connection to these peers is interrupted then the Receptor node will
attempt to re-establish the connection.


Receptor Controller Launch
--------------------------

**Receptor** Controllers are special nodes in the Receptor network in that they
are responsible for connecting other systems to the network in order to
distribute work. They do this by starting a local unix socket that other
services can connect to in order to send that work and receive results.

The **Receptor** Controller is launched using the ``controller`` subcommand::

  $ receptor controller <optionalargs>


Receptor Node Launch
--------------------

**Receptor** nodes participate in routing and/or execute work performed that
has been routed to them.

The **Receptor** Node is launched using the ``node`` subcommand::

  $ receptor node <optionalargs>

Other Launch Modes
------------------

* ``ping``: This sends a ping message to the target node and waits for a
  response.
* ``send``: Given the path to the **Controller** socket file this will send the
  raw payload to a given node along with the plugin to execute it and wait for
  the response.
