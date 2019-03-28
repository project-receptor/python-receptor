class ReceptorRuntimeError(RuntimeError): pass
class ReceptorMessageError(ValueError): pass
class ReceptorConfigError(Exception): pass

class UnknownDirective(ReceptorMessageError): pass
class UnknownMessageType(ReceptorMessageError): pass
