class ReceptorRuntimeError(RuntimeError):
    pass


class ReceptorBufferError(ReceptorRuntimeError):
    pass


class ReceptorMessageError(ValueError):
    pass


class ReceptorConfigError(Exception):
    pass


class UnknownDirective(ReceptorMessageError):
    pass


class InvalidDirectiveAction(ReceptorMessageError):
    pass


class UnknownMessageType(ReceptorMessageError):
    pass


class UnrouteableError(ReceptorMessageError):
    pass
