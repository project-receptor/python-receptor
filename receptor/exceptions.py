class ReceptorRuntimeError(RuntimeError): pass
class ReceptorConfigError(Exception): pass

class UnknownDirective(ReceptorRuntimeError): pass
