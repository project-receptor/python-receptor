import datetime
import logging

from .receptor import Receptor
from . import node
from . import controller

logger = logging.getLogger(__name__)


def run_as_controller(config):
    receptor = Receptor(config)
    logger.info(f'Starting up as node ID {receptor.node_id}')
    controller.mainloop(receptor, config.controller_socket_path)


def run_as_ping(config):
    logger.info(f'Sending ping to {config.ping_recipient}.')
    now = datetime.datetime.utcnow()
    controller.send_directive('receptor:ping', config.ping_recipient, now.isoformat(), config.ping_socket_path)


def run_as_send(config):
    logger.info(f'Sending a {config.send_directive} directive to {config.send_recipient}.')
    controller.send_directive(config.send_directive, config.send_recipient, config.send_payload, config.send_socket_path)


def run_as_node(config):
    receptor = Receptor(config)
    logger.info(f'Running as Receptor node with ID: {receptor.node_id}')
    node.mainloop(receptor, config.node_ping_interval)
