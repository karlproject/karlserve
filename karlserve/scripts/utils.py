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
