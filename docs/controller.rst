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
    controller.enable_server(["rnp://0.0.0.0:8888"])
    controller.run()

The server won't start listening until you call the ``run()`` method.

Starting the service is useful for letting other Receptor nodes connect to the Controller but
it's also possible to have the controller reach out to peers directly::

    controller.add_peer("rnp://10.0.0.1:8888")

Once the event loop is started with ``run()`` the connection will be established.

If the rest of your program is using asyncio you may already have an event loop, you can pass that
in when you initialize the controller::

    controller = receptor.Controller(config, loop=my_event_loop)

If you are managing the running of the event loop somewhere else in your code, you can pass the
event loop to the Controller and omit calling ``.run()``

Sending and Receiving Work
--------------------------

Now that we have the basics of initializing the Controller and starting a service lets look at
sending and receiving work

.. code-block:: python

    msgid = await controller.send(payload={"url": "https://github.com/status", "method": "GET"},
                                  recipient="othernode",
                                  directive="receptor_http:execute)

When a message is constructed for sending via the Receptor mesh, an identifier is generated and
returned. If you have sent several messages to the mesh you can use this identifier to distinguish
responses from one request to another. You should have another task elsewhere that can receive
responses, which we'll get to later. In the meantime

.. code-block:: python

    message = await controller.recv()
    print(f"{message.header.in_response_to} : {message.payload.readall()})

Plugins on Receptor nodes can send multiple messages in response to a single request and it's
useful to know when a plugin is done performing work

.. code-block:: python

    message = await controller.recv()
    print(f"{message.header.in_response_to} : {message.payload.readall()})
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
is return and the Controller shuts down

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
                asyncio.sleep(0.1)
            print("All done, Controller shutting down!")

        config = receptor.ReceptorConfig()
        controller = receptor.Controller(config)
        controller.run(relay_work)

Passing this task to *run()* is optional and it's entirely possible to just create this task and
just have the runloop be persistent

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
                asyncio.sleep(0.1)
            print("All done, Controller shutting down!")

        config = receptor.ReceptorConfig()
        controller = receptor.Controller(config)
        controller.loop.create_task(relay_work)
        controller.run()

Tasks that receive data
^^^^^^^^^^^^^^^^^^^^^^^

Receiving data is very similar to sending data in that it allows you to take a few different
approaches that match your use case. The Controller internally relies on an
`AsyncIO Queue <https://docs.python.org/3.6/library/asyncio-queue.html>`_ if you have your own
way of fetching events from this queue you can pass it to the Controller when you instantiate it

.. code-block:: python

    controller = receptor.Controller(config, queue=my_asyncio_queue)

Any responses will be received in the queue as they arrive to the Controller node. If you don't
have an existing queue, one is automatically created for you and is available at *controller.queue*

There is a helpful method on the controller that you can use to call and receive an event once they
come in: :meth:`receptor.controller.Controller.recv` lets take a look at how we can create a task
to consume an event one at a time from that queue

.. code-block:: python
    :linenos:

    def my_awesome_controller():
        async def read_responses():
            while True:
                message = await controller.recv()
                sent_message_id = message.header.get("in_response_to", None)
                if message.payload and sent_message_id:
                    print(f"I got a response and it said: {message.payload.readall().decode()}")
                    print(f"It was in response to {sent_message_id}")
                if message.header.get("eof", False):
                    print("The plugin was finished sending messages")

        config = receptor.ReceptorConfig()
        controller = receptor.Controller(config)
        controller.loop.create_task(read_responses())
        controller.run()

Combine this response handling task with the message sending tasks from the section above and you
have a complete Receptor controller system ready to be integrated.

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

    msg_id = controller.ping("some_other_node")

The responses appear in the response queue if/when it's received. The *msg_id* will match
the *in_response_to* key on the received message::

    message = await controller.recv()
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