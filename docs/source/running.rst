.. _running:

Configuring and Running Receptor
================================

Receptor nodes need to be configured to work together in order to be useful.
There isn't currently a mechanism for auto-discovery of Receptor nodes so it's
important to consider how nodes themselves will be configured to talk to one
another.

Each **Receptor** node can run a server that accepts connections from other
nodes. Simultaneously Receptor can be configured to connect directly to other
nodes. Once these connections are established they are treated the same way
with the exception that connections established by the node itself will attempt
to reestablish a connection that is lost.

Disabling The Node Server
-------------------------
