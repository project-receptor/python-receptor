import importlib
import configparser
import os
import uuid

DEFAULT_CONFIG = dict(
    server=dict(
        port=8888,
        address='0.0.0.0'
    ),
    components=dict(
        security_manager='receptor.security.MallCop',
        buffer_manager='receptor.buffers.memory.InMemoryBufferManager'
    ),
    peers=dict()
)

def py_class(class_spec):
    if class_spec not in SINGLETONS:
        module_name, class_name = class_spec.rsplit('.', 1)
        module_obj = importlib.import_module(module_name)
        class_obj = getattr(module_obj, class_name)
        SINGLETONS[class_spec] = class_obj()
    return SINGLETONS[class_spec]

CAST_MAP = dict(
    server=dict(
        port=int
    ),
    components=dict(
        security_manager=py_class,
        buffer_manager=py_class
    )
)

VALUELESS_SECTIONS = ['peers']

SINGLETONS = dict()

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
    
    def __getattr__(self, key):
        if key in VALUELESS_SECTIONS:
            return list(dict(self._parser.items(key)).keys())
        return ReceptorConfigSection(self._parser, key)

config = ReceptorConfig()

def get_node_id():
    if config.receptor.node_id:
        return config.receptor.node_id
    if not 'RECEPTOR_NODE_ID' in os.environ:
        node_id = uuid.uuid4()
        os.environ['RECEPTOR_NODE_ID'] = str(node_id)
        if os.path.exists(os.path.join(os.getcwd(), 'Pipfile')):
            with open(os.path.join(os.getcwd(), '.env'), 'w+') as ofs:
                ofs.write(f'\nRECEPTOR_NODE_ID={node_id}\n')
    return os.environ['RECEPTOR_NODE_ID']
