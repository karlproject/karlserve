from __future__ import with_statement

import logging
from karl.utils import asbool


def configure_log(**config):
    redislog_handler = None
    logger = logging.getLogger()
    for old_handler in logger.handlers:
        if isinstance(old_handler, NullHandler):
            logger.removeHandler(old_handler)
        if isinstance(old_handler, RedisLogHandler):
            redislog_handler = old_handler

    if not redislog_handler:
        redislog_handler = configure_redislog(**config)
        if redislog_handler:
            logger.addHandler(redislog_handler)


def configure_redislog(**config):
    if not asbool(config.get('redislog', 'False')):
        return None

    redisconfig = dict([(k[9:], v) for k, v in config.items()
                        if k.startswith('redislog.')])
    for intkey in ('port', 'db', 'expires'):
        if intkey in redisconfig:
            redisconfig[intkey] = int(intkey)

    debug = config.get('debug', False)
    if debug:
        level = logging.DEBUG
    else:
        level = logging.INFO
    return RedisLogHandler(redisconfig, level, config['get_current_instance'])


def set_subsystem(subsystem):
    logger = logging.getLogger()
    for handler in logger.handlers:
        if isinstance(handler, RedisLogHandler):
            handler.set_subsystem(subsystem)


class RedisLogHandler(logging.Handler):
    subsystem = 'general'

    def __init__(self, config, level, get_current_instance):
        logging.Handler.__init__(self, level=level)
        self.logs = {}
        self.config = config
        self.get_current_instance = get_current_instance

    def set_subsystem(self, subsystem):
        self.subsystem = subsystem

    def get_log(self):
        instance = self.get_current_instance()
        if instance is None:
            logging.getLogger(__name__).warn(
                "No instance is set.  Cannot log to redislog.")
            return
        log = self.logs.get(instance)
        if not log:
            from karl.redislog import RedisLog
            config = self.config.copy()
            prefix = config.get('prefix', 'karl')
            config['prefix'] = '%s.%s' % (prefix, instance)
            self.logs[instance] = log = RedisLog(**config)
        return log

    def emit(self, record):
        if record.name == __name__:
            # Avoid infinite recursion loop with warning emitted in get_log
            return

        log = self.get_log()
        if not log:
            return

        message = record.msg
        if record.args:
            try:
                message = message % record.args
            except ValueError:
                message = '%s: %s' % (message, str(record.args))

        exc_info = bool(record.exc_info)
        log.log(record.levelname, self.subsystem, message, exc_info)


# Copied verbatim from Python logging documentation
class NullHandler(logging.Handler):
    def emit(self, record):
        pass

