import logging
import subprocess
import sys


log = logging.getLogger(__name__)


def shell(cmd):
    """
    Run a command as though it were being called from a shell script.
    """
    log.info(cmd)
    return subprocess.check_call(cmd, shell=True)


def shell_capture(cmd):
    """
    Run a command and return the output as a string, as though running in
    backticks in bash.
    """
    log.debug(cmd)
    output = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]
    return output


def shell_pipe(cmd, data):
    """
    Run a command and return the it's input as a writable file object, for
    piping data to.
    """
    if len(data) < 100:
        logdata = data
    else:
        logdata = '[data]'
    log.info('%s < %s' % (cmd, data))
    pipe = subprocess.Popen(
        cmd, shell=True, stdin=subprocess.PIPE).communicate(data)


def shell_script(f):
    """
    Used as decorator for function that will be calling out to the shell.
    Catches subprocess.CalledProcessError and exits.  The subprocess is relied
    upon to report its own error message.
    """
    def wrapper(*args, **kw):
        try:
            return f(*args, **kw)
        except subprocess.CalledProcessError, e:
            sys.exit(1)
    return wrapper


def parse_dsn(dsn):
    """ Parse a postgresql dsn using a finite state machine.
    """
    SCANNING = 0
    IN_NAME = 1
    IN_VALUE = 2
    quote_chars = "'"""

    state = SCANNING
    token_begin = None
    name = None
    quote_char = None
    length = len(dsn)
    data = {}

    i = 0
    while i < length:
        ch = dsn[i]
        if state == SCANNING:
            if not ch.isspace():
                token_begin = i
                state = IN_NAME
            else:
                i += 1

        elif state == IN_NAME:
            if ch == '=':
                name = dsn[token_begin:i]
                i += 1
                next_ch = dsn[i]
                if next_ch in quote_chars:
                    quote_char = next_ch
                    i += 1
                token_begin = i
                state = IN_VALUE
            else:
                i += 1

        elif state == IN_VALUE:
            end = ch.isspace() if not quote_char else ch == quote_char
            if end:
                value = dsn[token_begin:i]
                data[name] = value
                name = value = quote_char = None
                state = SCANNING
            i += 1

    assert state in (SCANNING, IN_VALUE)
    if state == IN_VALUE:
        value = dsn[token_begin:]
        data[name] = value

    return data
