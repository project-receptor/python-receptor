import argparse
import configparser
import importlib
import logging
import os
import ssl

from .entrypoints import run_as_node, run_as_controller, run_as_ping, run_as_send
from .exceptions import ReceptorRuntimeError, ReceptorConfigError

logger = logging.getLogger(__name__)

SINGLETONS = {}
SUBCOMMAND_EXTRAS = {
    'node': {
        'hint': 'Run a Receptor node',
        'entrypoint': run_as_node,
    },
    'controller': {
        'hint': 'Run a Receptor controller',
        'entrypoint': run_as_controller,
    },
    'ping': {
        'hint': 'Tell the local controller to ping a node',
        'entrypoint': run_as_ping,
    },
    'send': {
        'hint': 'Send a directive to a node',
        'entrypoint': run_as_send,
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
            default_value='/var/lib/receptor',
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
        # Auth section options. This is a new section for the config file only,
        # so all of these options use `subparse=False`.
        self.add_config_option(
            section='auth',
            key='ssl_cert',
            default_value='',
            value_type='str',
            subparse=False,
            hint='Path to the SSL/TLS certificate chain file.',
        )
        self.add_config_option(
            section='auth',
            key='ssl_key',
            default_value='',
            value_type='str',
            subparse=False,
            hint='Path to the SSL/TLS certificate key file.',
        )
        # Receptor node options
        self.add_config_option(
            section='node',
            key='listen_address',
            default_value='0.0.0.0',
            value_type='str',
            hint='Set/override IP address to listen on. If not set here or in a config file, the default is 0.0.0.0/0.',
        )
        self.add_config_option(
            section='node',
            key='listen_port',
            default_value=8888,
            value_type='int',
            hint='Set/override TCP port to listen on. If not set here or in a config file, the default is 8888.',
        )
        self.add_config_option(
            section='node',
            key='peers',
            short_option='-p',
            long_option='--peer',
            default_value=None,
            value_type='list',
            listof='str',
            hint='Set/override peer nodes/controllers to connect to. Use multiple times for multiple peers.',
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
            key='ping_interval',
            default_value=-1,
            value_type='int',
            hint='If specified, the node will ping all other known nodes in the mesh every N seconds. The default is -1, meaning no pings are sent.',
        )
        # Controller options
        self.add_config_option(
            section='controller',
            key='socket_path',
            default_value='/var/run/receptor_controller.sock',
            value_type='path',
            hint='Path to control socket for controller commands.',
        )
        self.add_config_option(
            section='controller',
            key='listen_address',
            default_value='0.0.0.0',
            value_type='str',
            hint='Set/override IP address to listen on. If not set here or in a config file, the default is 0.0.0.0/0.',
        )
        self.add_config_option(
            section='controller',
            key='listen_port',
            default_value=8888,
            value_type='int',
            hint='Set/override TCP port to listen on. If not set here or in a config file, the default is 8888.',
        )
        self.add_config_option(
            section='controller',
            key='id',
            long_option='--node-id',
            default_value='',
            value_type='str',
            hint='Set/override controller node identifier. If unspecified here or in a config file, one will be automatically generated.',
        )
        # Ping options
        self.add_config_option(
            section='ping',
            key='socket_path',
            default_value='/var/run/receptor_controller.sock',
            value_type='path',
            hint='Path to control socket for controller commands.',
        )
        self.add_config_option(
            section='ping',
            key='count',
            default_value=0,
            value_type='int',
            hint='Number of pings to send. If unspecified here or in a config file pings will be continuously sent until interrupted.',
        )
        self.add_config_option(
            section='ping',
            key='delay',
            default_value=0,
            value_type='float',
            hint='The delay (in seconds) to wait between pings. If unspecified here or in a config file pings will be sent as soon as the previous response is received.',
        )
        self.add_config_option(
            section='ping',
            key='recipient',
            long_option='ping_recipient',
            default_value='',
            value_type='str',
            hint='Node ID of the Receptor node or controller to ping.',
        )
        # send options
        self.add_config_option(
            section='send',
            key='socket_path',
            default_value='/var/run/receptor_controller.sock',
            value_type='path',
            hint='Path to control socket for controller commands.',
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
            hint='Node ID of the Receptor node or controller to ping.',
        )
        self.add_config_option(
            section='send',
            key='payload',
            long_option='send_payload',
            default_value='',
            value_type='str',
            hint='Payload of the directive to send. Use - for stdin.',
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
            if value_type == 'list':
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

    def _enforce_entry_type(self, entry):
        if entry.value is not None:
            if entry.value_type == 'list':
                if not isinstance(entry.value, list):
                    entry.value = entry.value.split(',')
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
                return value
            else:
                return value
        except Exception as e:
            if value is None:
                return None
            raise ReceptorConfigError(e)

    def go(self):
        if not self._parsed_args:
            raise ReceptorRuntimeError("there are no parsed args yet")
        self._parsed_args.func(self)


    def get_client_ssl_context(self):
        if self.auth_ssl_cert:
            logger.debug("Loading SSL Client Context")
            return ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=self.auth_ssl_cert)
        else:
            return None

    def get_server_ssl_context(self):
        if self.auth_ssl_cert and self.auth_ssl_key:
            logger.debug("Loading SSL Server Context")
            sc = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            sc.load_cert_chain(self.auth_ssl_cert, self.auth_ssl_key)
            return sc
        else:
            return None

    def __getattr__(self, key):
        return self._config_options[key].value
