.. _messages:

Messages and Message Format
===========================

Headers and Payloads
--------------------

At the highest level, most messages (both Controller-sent directives and Plugin replies) are
composed of two parts: A header, and a payload.

Headers contain metadata about the message, such as the destination and sender. The payload is the
raw message containing the data that the node intended to send. Normally senders and consumers of
the Receptor mesh don't have to worry about the details of the transmission format of Messages but
Controller's need an understanding of some elements of the header and both Controllers and Plugins
need to understand how payloads are accepted and transmitted.

Headers on Response messages typically contain the following information

* in_response_to - The message id of the original request that started the work
* serial - A number representing the numerical sequence of responses from a plugin
* timestamp - utc timestamp representing when the reply was sent
* code - If this value is 1, then a Receptor error occurred and the payload contains the details
    A value of 0 represents a normal response that did not record a Receptor error
* eof - If true, this response represents the last message sent, it is emitted once the plugin
    returns

Note that some messages will not have a payload and are represented only as headers. An EOF
message response from a plugin is one such message, other messages used internally by Receptor
also do not contain payloads.

Message Transmission Architecture
---------------------------------