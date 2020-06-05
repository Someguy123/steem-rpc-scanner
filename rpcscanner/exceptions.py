from privex.helpers import empty


class RPCScannerException(Exception):
    """Base exception for custom exceptions part of this app"""
    pass


class ServerDead(RPCScannerException):
    def __init__(self, message: str, orig_ex=None, http_status=None, **kwargs):
        super(ServerDead, self).__init__(message)
        self.message = message
        self.orig_ex = orig_ex
        self.http_status = http_status
        self.response = kwargs.get('response', None)
        self.host = kwargs.get('host', None)


class ValidationError(RPCScannerException):
    pass


class RPCError(RPCScannerException):
    def __init__(self, message: str, error_msg=None, error_code=None, **kwargs):
        super(RPCError, self).__init__(message)
        self.message = message
        self.error_msg = error_msg
        self.error_code = error_code
        self.response = kwargs.get('response', None)
        self.host = kwargs.get('host', None)
        self.http_status = kwargs.get('http_status', 500)

    def __str__(self):
        f = f"{self.message}"
        if not empty(self.host): f += f" (host: {self.host})"
        if not empty(self.error_code, True): f += f" Server error code: {self.error_code}"
        if not empty(self.error_msg): f += f" Server error message: {self.error_msg}"
        return f
    
    def __repr__(self):
        return f'<{self.__class__.__name__} message="{self.message[0:15]} ..." error_msg="{self.error_msg}" ' \
               f'error_code={self.error_code} http_status={self.http_status} />'


class RPCMethodNotSupported(RPCError):
    pass


class RPCInvalidArguments(RPCError):
    pass


class RPCInvalidArgumentType(RPCInvalidArguments):
    pass

