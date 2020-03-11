import argparse
import configparser
import importlib
import logging
import os
import ssl

from .entrypoints import run_as_node, run_as_ping, run_as_send, run_as_status
from .exceptions import ReceptorRuntimeError, ReceptorConfigError

logger = logging.getLogger(__name__)

SINGLETONS = {}
SUBCOMMAND_EXTRAS = {
    'node': {
        'hint': 'Run a Receptor node',
        'entrypoint': run_as_node,
        'is_ephemeral': False,
    },
    'ping': {
        'hint': 'Ping a Receptor node',
        'entrypoint': run_as_ping,
        'is_ephemeral': True,
    },
    'send': {
        'hint': 'Send a directive to a node',
        'entrypoint': run_as_send,
        'is_ephemeral': True,
    },
    'status': {
        'hint': 'Display status of the Receptor network',
        'entrypoint': run_as_status,
        'is_ephemeral': True,
    },
}


def py_class(class_spec):
    if class_spec not in SINGLETONS:
        module_name, class_name = class_spec.rsplit('.', 1)
        module_obj = importlib.import_module(module_name)
        class_obj = getattr(module_obj, class_name)
        SINGLETONS[class_spec] = class_obj()
    return SINGLETONS[class_spec]


class ConfigOption:
    def __init__(self, value, value_type, listof=None):
        self.value = value
        self.value_type = value_type
        self.listof = listof


class ReceptorConfig:
    def __init__(self, args=None):
        self._config_options = {}
        self._cli_args = argparse.ArgumentParser("receptor")
        self._cli_sub_args = self._cli_args.add_subparsers()
        self._parsed_args = None
        self._config_file = configparser.ConfigParser(allow_no_value=True, delimiters=('=',))
        self._is_ephemeral = False

        # Default options, which apply to all sub-commands.
        self.add_config_option(
            section='default',
            key='node_id',
            default_value='',
            value_type='str',
            hint='Set/override node identifier. If unspecified here or in a config file, one will be automatically generated.',
        )
        self.add_config_option(
            section='default',
            key='config',
            short_option='-c',
            default_value='/etc/receptor/receptor.conf',
            value_type='path',
            hint='Path to the Receptor configuration file.',
        )
        self.add_config_option(
            section='default',
            key='data_dir',
            short_option='-d',
            default_value=None,
            value_type='path',
            hint='Path to the directory where Receptor stores its database and metadata.',
        )
        self.add_config_option(
            section='default',
            key='debug',
            default_value=None,
            set_value=True,
            value_type='bool',
            hint='Emit debugging output.',
        )
        default_max_workers = min(32, os.cpu_count() + 4)
        self.add_config_option(
            section='default',
            key='max_workers',
            default_value=default_max_workers,
            value_type='int',
            hint='Size of the thread pool for worker threads. If unspecified, defaults to {}'.format(default_max_workers),
        ),
        # Auth section options. This is a new section for the config file only,
        # so all of these options use `subparse=False`.
        self.add_config_option(
            section='auth',
            key='server_cert',
            default_value='',
            value_type='str',
            subparse=False,
            hint='Path to the SSL/TLS server certificate file.',
        )
        self.add_config_option(
            section='auth',
            key='server_key',
            default_value='',
            value_type='str',
            subparse=False,
            hint='Path to the SSL/TLS server certificate key file.',
        )
        self.add_config_option(
            section='auth',
            key='server_ca_bundle',
            default_value=None,
            value_type='str',
            subparse=False,
            hint='Path to the CA bundle used by clients to verify servers.',
        )
        self.add_config_option(
            section='auth',
            key='client_cert',
            default_value='',
            value_type='str',
            subparse=False,
            hint='Path to the SSL/TLS client certificate file.',
        )
        self.add_config_option(
            section='auth',
            key='client_key',
            default_value='',
            value_type='str',
            subparse=False,
            hint='Path to the SSL/TLS client certificate key file.',
        )
        self.add_config_option(
            section='auth',
            key='client_verification_ca',
            default_value=None,
            value_type='str',
            subparse=False,
            hint='Path to the CA bundle used by servers to verify clients.',
        )
        self.add_config_option(
            section='auth',
            key='server_cipher_list',
            default_value=None,
            value_type='str',
            subparse=False,
            hint='TLS cipher list for use by the server.',
        )
        self.add_config_option(
            section='auth',
            key='client_cipher_list',
            default_value=None,
            value_type='str',
            subparse=False,
            hint='TLS cipher list for use by the client.',
        )
        # Receptor node options
        self.add_config_option(
            section='node',
            key='listen',
            default_value=['rnp://0.0.0.0:8888'],
            value_type='list',
            hint='Set/override IP address and port to listen on. If not set here or in a config file, the default is rnp://0.0.0.0:8888.',
        )
        self.add_config_option(
            section='node',
            key='peers',
            short_option='-p',
            long_option='--peer',
            default_value=[],
            value_type='list',
            listof='str',
            hint='Set/override peer nodes to connect to. Use multiple times for multiple peers.',
        )
        self.add_config_option(
            section='node',
            key='server_disable',
            default_value=False,
            value_type='bool',
            hint='Disable the server function and only connect to configured peers',
        )
        self.add_config_option(
            section='node',
            key='stats_enable',
            default_value=None,
            set_value=True,
            value_type='bool',
            hint="Enable Prometheus style stats port",
        )
        self.add_config_option(
            section='node',
            key='stats_port',
            default_value=8889,
            value_type='int',
            hint='Port to listen for requests to show stats',
        )
        self.add_config_option(
            section='node',
            key='keepalive_interval',
            default_value=-1,
            value_type='int',
            hint='If specified, the node will ping all other known nodes in the mesh every N seconds. The default is -1, meaning no pings are sent.',
        )
        self.add_config_option(
            section='node',
            key='groups',
            short_option='-g',
            long_option='--group',
            default_value=[],
            value_type='list',
            listof='str',
            hint='Define membership in one or more groups to aid in message routing',
        )
        self.add_config_option(
            section='node',
            key='ws_extra_headers',
            long_option='--ws_extra_header',
            default_value=[],
            value_type='key-value-list',
            hint='Set additional headers to provide when connecting to websocket peers.',
        )
        # ping options
        self.add_config_option(
            section='ping',
            key='peer',
            default_value='localhost:8888',
            value_type='str',
            hint='The peer to relay the ping directive through. If unspecified here or in a config file, localhost:8888 will be used.'
        )
        self.add_config_option(
            section='ping',
            key='count',
            default_value=4,
            value_type='int',
            hint='Number of pings to send. If set to zero, pings will be continuously sent until interrupted.',
        )
        self.add_config_option(
            section='ping',
            key='delay',
            default_value=1,
            value_type='float',
            hint='The delay (in seconds) to wait between pings. If set to zero,'
                 'pings will be sent as soon as the previous response is received.',
        )
        self.add_config_option(
            section='ping',
            key='recipient',
            long_option='ping_recipient',
            default_value='',
            value_type='str',
            hint='Node ID of the Receptor node to ping.',
        )
        self.add_config_option(
            section='ping',
            key='ws_extra_headers',
            long_option='--ws_extra_header',
            default_value=[],
            value_type='key-value-list',
            hint='Set additional headers to provide when connecting to websocket peers.',
        )
        # send options
        self.add_config_option(
            section='send',
            key='peer',
            default_value='localhost:8888',
            value_type='str',
            hint='The peer to relay the directive through. If unspecified here or in a config file, localhost:8888 will be used.'
        )
        self.add_config_option(
            section='send',
            key='directive',
            default_value='',
            value_type='str',
            hint='Directive to send.',
        )
        self.add_config_option(
            section='send',
            key='recipient',
            long_option='send_recipient',
            default_value='',
            value_type='str',
            hint='Node ID of the Receptor node to ping.',
        )
        self.add_config_option(
            section='send',
            key='payload',
            long_option='send_payload',
            default_value='',
            value_type='str',
            hint='Payload of the directive to send. Use - for stdin or give the path to a file to transmit the file contents.',
        )
        self.add_config_option(
            section='send',
            key='ws_extra_headers',
            long_option='--ws_extra_header',
            default_value=[],
            value_type='list',
            hint='Set additional headers to provide when connecting to websocket peers.',
        )
        # status options
        self.add_config_option(
            section='status',
            key='peer',
            default_value='localhost:8888',
            value_type='str',
            hint='The peer to access the mesh through. If unspecified here or in a config file, localhost:8888 will be used.'
        )
        self.add_config_option(
            section='status',
            key='ws_extra_headers',
            long_option='--ws_extra_header',
            default_value=[],
            value_type='key-value-list',
            listof='str',
            hint='Set additional headers to provide when connecting to websocket peers.',
        )
        # Component options. These are also only used in a config section
        # like auth, so they also set `subparse=False`.
        self.add_config_option(
            'components',
            'security_manager',
            default_value='receptor.security.MallCop',
            value_type=py_class,
            subparse=False,
            hint='',
        )
        self.add_config_option(
            'components',
            'buffer_manager',
            default_value='receptor.buffers.file.FileBufferManager',
            value_type=py_class,
            subparse=False,
            hint='',
        )

        self.parse_options(args)

    def add_config_option(self, section, key, cli=True, short_option='', long_option='',
                          default_value=None, set_value=None, value_type=None, listof=None, subparse=True,
                          hint=None):
        config_entry = '%s_%s' % (section, key)
        if cli:
            # for lists, we switch the action from 'store' to 'append'
            action = 'store'
            if value_type == 'list' or value_type == 'key-value-list':
                action = 'append'
            if value_type == 'bool':
                action = 'store_const'
            # unless specified, the long_option name is the key (with underscores turned into dashes)
            if not long_option:
                long_option = '--%s' % (key.replace('_', '-'),)
            # because we're building this on the fly, it's easier to create the args/kwargs
            # for argparse like this instead of trying to actually call the method with all
            # of the positional args correctly
            args = []
            if short_option:
                args.append(short_option)
            args.append(long_option)
            kwargs = {
                'help': hint,
                'action': action,
            }
            # if the long option doesn't start with '--' it's a positional arg, in which
            # case we don't want to use dest= because it will cause an argparse conflict
            if long_option.startswith('--'):
                kwargs['dest'] = config_entry
            # some special handling for bools to make sure we don't always override lower
            # precedence options with the cli default (which happens if we tried to use
            # store_true or store_false for bools).
            if value_type == 'bool':
                kwargs['const'] = set_value
            # if we're in the default section, or if we explictly don't want this section
            # turned into a subparser, we add the option directly, otherwise we put it in
            # a subparser based on the section name
            if section == 'default' or not subparse:
                self._cli_args.add_argument(*args, **kwargs)
            else:
                try:
                    subparser = self._cli_sub_args.choices[section]
                except KeyError:
                    sub_extra = SUBCOMMAND_EXTRAS.get(section, None)
                    if sub_extra:
                        subparser = self._cli_sub_args.add_parser(section, help=sub_extra['hint'])
                        subparser.set_defaults(func=sub_extra['entrypoint'])
                        subparser.set_defaults(ephemeral=sub_extra['is_ephemeral'])
                subparser.add_argument(*args, **kwargs)

        # finally, we add the ConfigOption to the internal dict for tracking
        self._config_options[config_entry] = ConfigOption(default_value, value_type, listof)

    def _get_config_value(self, key, ignore_config_file=False):
        value = None

        # lowest precedence is the config file
        (section, section_key) = key.split('_', 1)
        if not ignore_config_file and section in self._config_file and self._config_file[section]:
            try:
                value = self._config_file[section][section_key]
            except KeyError:
                pass
        # next layer of precedence is environment variables. All env
        # variable names are of the form RECEPTOR_SECTION_{KEY_NAME}
        # (the 'key' variable contains both the section and key name)
        env_name = 'RECEPTOR_' + key.upper()
        env_value = os.environ.get(env_name, None)
        if env_value is not None:
            value = env_value
        # finally, the cli args are the highest level of precedence
        cli_value = getattr(self._parsed_args, key, None)
        if cli_value is not None:
            value = cli_value
        # finally return whatever the value was set to (or not)
        return value

    def parse_options(self, args):
        # first we parse the cli args
        self._parsed_args = self._cli_args.parse_args(args)
        # we manually force the config entry to be parsed first, since
        # we need it before we do anything else
        config_entry = self._config_options['default_config']
        config_path = self._get_config_value('default_config', ignore_config_file=True)
        if config_path is not None:
            config_entry.value = config_path
        self._enforce_entry_type(config_entry)
        # next we read the config file
        self._config_file.read([config_entry.value])
        # then we loop through our config options, based on the option
        # precedence of CLI > environment > config file
        for key in self._config_options:
            # we already did this, so lets not waste time doing it over
            if key == 'default_config':
                continue
            entry = self._config_options[key]
            value = self._get_config_value(key)
            if value is not None:
                entry.value = value
            # because env variables and configparser do not enforce the
            # value type, we do it now to ensure we have the type we want
            self._enforce_entry_type(entry)
        # Parse plugin_ sections to populate plugin configuration
        self._config_options['plugins'] = {}
        if self._config_file:
            for section in filter(lambda x: x.startswith("plugin_"), self._config_file.sections()):
                self._config_options['plugins'][section.replace("plugin_", "")] = dict(self._config_file[section])
        # If we did not get a data_dir from anywhere else, use a default
        if self._config_options['default_data_dir'].value is None:
            if self._is_ephemeral:
                self._config_options['default_data_dir'].value = '/tmp/receptor'
            else:
                self._config_options['default_data_dir'].value = '/var/lib/receptor'

    def _enforce_entry_type(self, entry):
        if entry.value is not None:
            if entry.value_type == 'list' or entry.value_type == 'key-value-list':
                if not isinstance(entry.value, list):
                    entry.value = entry.value.split(',')
                if entry.value_type == 'key-value-list':
                    entry.value = [(key.strip(), value.strip()) for key, sep, value in [s.partition(':') for s in entry.value]]
                else:
                    for idx, value in enumerate(entry.value):
                        entry.value[idx] = self._enforce_value_type(value, entry.listof)
            else:
                entry.value = self._enforce_value_type(entry.value, entry.value_type)

    def _enforce_value_type(self, value, value_type):
        try:
            if callable(value_type):
                return value_type(value)
            elif value_type == 'int' and not isinstance(value, int):
                return int(value)
            elif value_type == 'float' and not isinstance(value, float):
                return float(value)
            elif value_type == 'str' and not isinstance(value, str):
                return '%s' % (value,)
            elif value_type == 'bool' and not isinstance(value, bool):
                if isinstance(value, str):
                    if value.lower() in ('yes', 'y', 'true'):
                        return True
                    else:
                        return False
                elif isinstance(value, int):
                    if value != 0:
                        return True
                    else:
                        return False
                else:
                    raise Exception("could not convert '%s' (type: %s) to a boolean value" % (value, type(value)))
            elif value_type == 'path':
                # FIXME: implement, or do we care if it's really a path and not just a string?
                return os.path.expanduser(value)
            else:
                return value
        except Exception as e:
            if value is None:
                return None
            raise ReceptorConfigError(e)

    def go(self):
        if not self._parsed_args:
            raise ReceptorRuntimeError("there are no parsed args yet")
        elif not hasattr(self._parsed_args, 'func'):
            raise ReceptorRuntimeError("you must specify a subcommand (%s)." % (", ".join(SUBCOMMAND_EXTRAS.keys()),))
        self._is_ephemeral = self._parsed_args.ephemeral
        self._parsed_args.func(self)

    def get_ssl_context(self, context_type):
        if context_type == 'server':
            return self.get_server_ssl_context()
        elif context_type == 'client':
            return self.get_client_ssl_context()
        else:
            raise ReceptorRuntimeError(f"Unknown SSL context type {context_type}")

    def get_client_ssl_context(self):
        logger.debug("Loading TLS Client Context")
        ca_bundle = self.auth_server_ca_bundle
        ca_bundle = ca_bundle if ca_bundle else None   # Make false-like values like '' explicitly None
        sc = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        sc.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
        if self.auth_client_cipher_list:
            sc.set_ciphers(self.auth_client_cipher_list)
        sc.verify_mode = ssl.CERT_REQUIRED
        if self.auth_server_ca_bundle:
            sc.load_verify_locations(self.auth_server_ca_bundle)
        else:
            sc.load_default_certs(ssl.Purpose.SERVER_AUTH)
        if self.auth_client_cert and self.auth_client_key:
            sc.load_cert_chain(self.auth_client_cert, self.auth_client_key)
        return sc

    def get_server_ssl_context(self):
        logger.debug("Loading TLS Server Context")
        ca_bundle = self.auth_client_verification_ca
        ca_bundle = ca_bundle if ca_bundle else None   # Make false-like values like '' explicitly None
        sc = ssl.SSLContext(ssl.PROTOCOL_TLS)
        sc.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3 | ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_TLSv1_2
        if self.auth_server_cipher_list:
            sc.set_ciphers(self.auth_server_cipher_list)
        if self.auth_client_verification_ca:
            sc.load_verify_locations(self.auth_client_verification_ca)
            sc.verify_mode = ssl.CERT_REQUIRED
            sc.check_hostname = False
        else:
            sc.load_default_certs(ssl.Purpose.CLIENT_AUTH)
        sc.load_cert_chain(self.auth_server_cert, self.auth_server_key)
        return sc

    def __getattr__(self, key):
        value = self._config_options[key]
        if type(value) is dict:
            return value
        else:
            return self._config_options[key].value
