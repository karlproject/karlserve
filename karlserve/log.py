from __future__ import with_statement

import logging
from logging.handlers import SysLogHandler
import os
import time

LOG_NAME = 'karl.system'


def get_logger():
    logger = logging.getLogger(LOG_NAME)
    if not logger.handlers:
        logger.addHandler(NullHandler())
    return logger


def configure_log(**config):
    debug = config.get('debug', False)
    if debug:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logger = logging.getLogger(LOG_NAME)
    logger.setLevel(level)

    error_monitor_handler = None
    for old_handler in logger.handlers:
        if isinstance(old_handler, NullHandler):
            logger.removeHandler(old_handler)
        if isinstance(old_handler, ErrorMonitorHandler):
            error_monitor_handler = old_handler

    # get_current_instance is passed in here rather than imported to prevent
    # circular import with instance.py
    error_monitor_dir = config['error_monitor_dir']
    get_current_instance = config['get_current_instance']
    if error_monitor_handler is None:
        error_monitor_handler = ErrorMonitorHandler(
            os.path.abspath(error_monitor_dir),
            get_current_instance
        )
        logger.addHandler(error_monitor_handler)


def set_subsystem(subsystem):
    logger = get_logger()
    for handler in logger.handlers:
        if isinstance(handler, ErrorMonitorHandler):
            handler.set_subsystem(subsystem)


class ErrorMonitorHandler(logging.Handler):
    """
    Provides a means of setting error status of arbitrary subsystems which can
    then be monitored by external observers.  The error states for all
    subsystems are stored in a single folder, with each subsystem represented
    by a single text format file.  The file is composed of N number of error
    entries separated by the keywork, 'ERROR' on a single line by itself.  The
    entries themselves are free format text.  Presence of error entries
    indicates to the monitoring service that the subsystem is in an error
    state.  The error state is cleared by removing all entries from the
    subsystem's file.
    """
    subsystem = None

    def __init__(self, path, get_current_instance):
        logging.Handler.__init__(self, logging.ERROR)

        if not os.path.exists(path):
            os.makedirs(path)
        self.path = path
        self.get_current_instance = get_current_instance

    def set_subsystem(self, subsystem):
        self.subsystem = subsystem

    def emit(self, record):
        # Don't do anything if no subsystem is configured
        if self.subsystem is None:
            return

        instance = self.get_current_instance()
        path = os.path.join(self.path, instance)
        if not os.path.exists(path):
            os.makedirs(path)
        filepath = os.path.join(path, self.subsystem)
        with open(filepath, 'a') as out:
            print >>out, 'ENTRY'
            print >>out, time.ctime()
            print >>out, self.format(record)


# Copied verbatim from Python logging documentation
class NullHandler(logging.Handler):
    def emit(self, record):
        pass

