.. _plugins:

Writing a Receptor Plugin
=========================

The page :ref:`term_work` covers the basics of plugins and messages and how they related to nodes.

A plugin is a python module that exposes one or more functions to the Receptor service. These
plugins are installed in the same environment and on the same system as a Receptor node. The
modules themselves don't have to run standalone, instead Receptor discovers them when it starts
and advertises that to other nodes. When work comes into a node it includes some information
about which plugin it should run and Receptor will import and call the requested function.

Plugins don't specifically have to be aware that Runner is operating under asyncio, instead
they are launched using a thread. Each plugin is given three parameters

* The *message* data sent from the Controller
* Any *configuration* specifically defined for it, which includes some details about the receptor
  node that sent the message
* A *queue* to place responses into. These responses are delivered back to the Controller
  immediately when they are placed into the queue

There are some great example plugins hosted in the
`Receptor Github Organization <https://github.com/project-receptor/>`_
The simplest ones are the `sleep plugin <https://github.com/project-receptor/receptor-sleep>`_ and
the `http plugin <https://github.com/project-receptor/receptor-http>`_

Module level documentation can be found in :mod:`receptor.plugin_utils`

Defining the entrypoint
-----------------------

When writing a python module to be used as a Receptor plugin, there are two things you need to
do, first is defining the *entrypoint*. This is typically done in your *setup.py* and recorded
by the python environment at install time

.. code-block:: python

    entry_points={
        'receptor.worker': 
            'your_package_name = your_package_name.your_module',
    }

Writing the entrypoint
----------------------

The last thing you'll need to do is write the actual function that Receptor will call, when doing
this you'll need to make sure this function is decorated with a special decorated that's provided
by receptor itself

.. code-block:: python
    :linenos:

    import receptor

    @receptor.plugin_export(payload_type=receptor.BYTES_PAYLOAD)
    def execute(message, config, result_queue):
        print(f"I just received {message.decode()}")
        result_queue.put("My plugin ran!")

That's it! When a controller wants to use this plugin they'll use the directive
**your_module:execute**

In the above example we used the payload type *receptor.BYTES_PAYLOAD* which told Receptor that
we wanted the incoming message delivered as `bytes`. You have 3 options here, depending on how you
expect to handle the data:

BYTES_PAYLOAD
    A value of type `bytes`.

BUFFER_PAYLOAD
    A value that contains a `read()` method so that you can treat the payload as a file handle.

FILE_PAYLOAD
    A temp file path that you can `open()` or do what you want with. This file will be removed once
    your function returns.

Caveats and Expected Behavior
-----------------------------

Plugins are expected to not run forever, there's no way for a controller to send multiple messages
to a single instance of a plugin, but a plugin can send multiple responses back to a controller.

Multiple instances of a plugin can be run at the same time corresponding to the number of times
the plugin is invoked by one or more controllers. There is an upper limit to the number of
simultaneous instances allowed to run, other invocations will wait until older ones are finished.

The plugin itself is intended to be mostly stateless and to receive all of the information it
needs to perform work from a controller. If additional configuration is needed it's recommended
that it read it fetch it at plugin invocation time.

Whenever a plugin finishes by *returning*, a final *EOF* message is sent back to the controller
so that caller knows when the work is done.

Controllers can get details about work that is running a remote Receptor node by sending a *ping*
