.. _controller:

Implementing the Controller
===========================

As mentioned in :ref:`intro` Controllers are special types of *Nodes* that link a larger
application or product to a Receptor mesh, their job is to send messages containing work
to plugins on other nodes. You can have one or many of these on the mesh.

Module details for the controller are available in :mod:`receptor.controller`
The command line interface for Receptor also uses the controller, those entrypoints are
great examples of how to start and run nodes :mod:`receptor.entrypoints`

Writing a basic Controller
--------------------------

Receptor is written to use Python's asyncio system and because of that any interface needs to
be asyncio aware. Lets look at the most basic usage of the Controller

.. code-block:: python
    :linenos:

    import receptor
    config = receptor.ReceptorConfig() # Initialize the receptor configuration
    controller = receptor.Controller(config) # Initialize a Receptor Controller
    controller.run()

The last line starts an asyncio event loop that will not return until the Controller is shut down.

This isn't very interesting. We should start a listener that will accept connections from other
receptor nodes

.. code-block:: python
    :linenos:
    :lineno-start: 3

    controller = receptor.Controller(config)
    controller.enable_server(["rnp://0.0.0.0:7323"])
    controller.run()

The server won't start listening until you call the ``run()`` method.

Starting the service is useful for letting other Receptor nodes connect to the Controller but
it's also possible to have the controller reach out to peers directly::

    controller.add_peer("rnp://10.0.0.1:7323")

Once the event loop is started with ``run()`` the connection will be established.

If the rest of your program is using asyncio you may already have an event loop, you can pass that
in when you initialize the controller::

    controller = receptor.Controller(config, loop=my_event_loop)

If you are managing the running of the event loop somewhere else in your code, you can pass the
event loop to the Controller and omit calling ``.run()``

Sending and Receiving Work
--------------------------

Now that we have the basics of initializing the Controller and starting a service lets look at
sending and receiving work::

.. code-block:: python

    msgid = await controller.send(payload={"url": "https://github.com/status", "method": "GET"},
                                  recipient="othernode",
                                  directive="receptor_http:execute,
                                  response_handler=receive_response)

When a message is constructed for sending via the Receptor mesh, a message identifier is generated and
returned. Reply traffic referring to this message identifier will be passed to the ``response_handler``
callback. The final reply message will have an "eof" header. This callback can be implemented as follows:

.. code-block:: python

    async def receive_response(message)):
        print(f"{message.header} : {message.payload.readall()}")
        if message.header.get("eof", False):
            print("Work finished!")

Using asyncio tasks for Sending and Receiving
---------------------------------------------

It may be necessary to set up asyncio tasks that are responsible for monitoring another part of the
system for work that needs to be sent to Receptor nodes as well as watching for replies from the
mesh.

Tasks that send data
^^^^^^^^^^^^^^^^^^^^

One approach that you can take is to create an async task that looks for work and pass that to the
Controller's *run()* method. This way, when you are finished checking for work all you need to do
is return and the Controller shuts down::

.. code-block:: python
    :linenos:

    def my_awesome_controller():
        async def relay_work():
            while True:
                work_thing = get_some_work()
                if work_thing:
                    controller.send(
                        payload=work_thing,
                        recipient="my_other_receptor_node",
                        directive="receptor_plugin:execute"
                    )
                else:
                    if am_i_done:
                        break
            print("All done, Controller shutting down!")

        config = receptor.ReceptorConfig()
        controller = receptor.Controller(config)
        controller.run(relay_work)

Passing this task to *run()* is optional and it's entirely possible to just create this task and
have the run loop be persistent::

.. code-block:: python
    :linenos:

        config = receptor.ReceptorConfig()
        controller = receptor.Controller(config)
        controller.loop.create_task(relay_work)
        controller.loop.create_task(some_other_task)
        controller.run()

Unlike the first example, this will not exit when :meth:`relay_work` and :meth:`some_other_task`
are complete.

Tasks that receive data
^^^^^^^^^^^^^^^^^^^^^^^

As described above, data is received through a callback provided to the
:meth:`receptor.controller.Controller.send` method.  We can extend the sample controller
to receive reply traffic as follows::

.. code-block:: python
    :linenos:

    def my_awesome_controller():

        async def handle_response(message):
            if message.payload:
                print(f"I got a response and it said: {message.payload.readall().decode()}")
                print(f"It was in response to {message.header.get("in_response_to", None)}")
            if message.header.get("eof", False):
                print("The plugin was finished sending messages")

        async def relay_work():
            while True:
                work_thing = get_some_work()
                if work_thing:
                    controller.send(
                        payload=work_thing,
                        recipient="my_other_receptor_node",
                        directive="receptor_plugin:execute",
                        response_handler=handle_response
                    )
                else:
                    if am_i_done:
                        break
            print("All done, Controller shutting down!")

        config = receptor.ReceptorConfig()
        controller = receptor.Controller(config)
        controller.run(relay_work)

Getting information about the mesh
----------------------------------

Each individual Node on a network has a view of the rest of the nodes and routes interconnecting
the mesh and a Controller is no different. It may be necessary for a Controller's application to
track and manage that information internally, as well as perform health and latency checks on other
nodes.

Route table and capabilities
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Once you have called *.run()* or have an event loop running, you'll be able to introspect:

* Nodes that exist on the mesh::

    controller.receptor.router.get_nodes()

* Edges between nodes::

    controller.receptor.router.get_edges()

* Node capabilities::

    controller.receptor.router.node_capabilities()

You can find more details in :mod:`receptor.router`

Pings and Health Checks
^^^^^^^^^^^^^^^^^^^^^^^

*ping* is a fundamental command to both node keepalives and health checking connected nodes
anywhere in the mesh. Ping not only sends back timing information that can help you check
mesh latency between the controller and a node, it also returns information about what work
is currently being executed.

Sending a ping works a lot like sending a normal message as in the examples above, except
there is a special controller method for it: :meth:`receptor.controller.Controller.ping`::

    def handle_ping_response(message):
        print(f"Ping response with content {message.payload.readall().decode()}")

    controller.ping("some_other_node", response_handler=handle_ping_response)

The content of a ping response looks as follows::

    pprint(message.payload.readall().decode())
    {
    "initial_time":{
        "_type":"datetime.datetime",
        "value":1584663304.815156
    },
    "response_time":{
        "_type":"datetime.datetime",
        "value":1584663305.037581
    },
    "active_work":[
        {
            "id":291723580643927245576334265826187768140,
            "directive":"receptor_sleep:execute",
            "sender":"89abc47c-9d8f-41fe-be3b-23d655b0b73b"
        }
    ]
    }