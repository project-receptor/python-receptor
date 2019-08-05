import importlib
import configparser
import ssl
import logging

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = dict(
    server=dict(
        port=8888,
        address='0.0.0.0',
        server_enable=True,
        debug=False,
        ssl_certificate='',
        ssl_key='',
    ),
    receptor=dict(
        node_id=None,
    ),
    peers=dict(),
    components=dict(
        security_manager='receptor.security.MallCop',
        buffer_manager='receptor.buffers.memory.InMemoryBufferManager'
    ),
)
VALUELESS_SECTIONS = ['peers']
SINGLETONS = {}


def py_class(class_spec):
    if class_spec not in SINGLETONS:
        module_name, class_name = class_spec.rsplit('.', 1)
        module_obj = importlib.import_module(module_name)
        class_obj = getattr(module_obj, class_name)
        SINGLETONS[class_spec] = class_obj()
    return SINGLETONS[class_spec]


CAST_MAP = dict(
    server=dict(
        port=int,
        server_enable=lambda val: val == "True",
        debug=lambda val: val == "True",
    ),
    peers=dict(),
    receptor=dict(),
    components=dict(
        security_manager=py_class,
        buffer_manager=py_class
    )
)


class ReceptorConfigSection:
    def __init__(self, parser, section):
        self._parser = parser
        self._section = section
    
    def __getattr__(self, key):
        if not self._parser.has_section(self._section):
            return None
        to_return = self._parser.get(self._section, key)
        cast_fn = CAST_MAP.get(self._section, {}).get(key, None)
        if cast_fn:
            return cast_fn(to_return)
        return to_return


class ReceptorConfig:
    def __init__(self, config_path=None, cmdline_args=None):
        self._parser = configparser.ConfigParser(allow_no_value=True, delimiters=('=',))
        self._parser.read_dict(DEFAULT_CONFIG)
        if config_path:
            self._parser.read([config_path])
        if cmdline_args:
            self._parser.read_dict(cmdline_args)

    def get_client_ssl_context(self):
        if self.server.ssl_certificate:
            logger.debug("Loading SSL Client Context")
            return ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=self.server.ssl_certificate)
        else:
            return None

    def get_server_ssl_context(self):
        if self.server.ssl_certificate and self.server.ssl_key:
            sc = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            sc.load_cert_chain(self.server.ssl_certificate, self.server.ssl_key)
            logger.debug("Loading SSL Server Context")
            return sc
        else:
            return None
    
    def __getattr__(self, key):
        if key in VALUELESS_SECTIONS:
            return list(dict(self._parser.items(key)).keys())
        return ReceptorConfigSection(self._parser, key)
