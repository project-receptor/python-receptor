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

Starting the listening service
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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

Getting information about the mesh
----------------------------------