"""Initialize logging for the rule processor."""
import logging
import os

FUNCTION_NAME = 'rule_processor'

# Create a package level logger to import
LEVEL = os.environ.get('LOGGER_LEVEL', 'INFO').upper()

# Cast integer levels to avoid a ValueError
if LEVEL.isdigit():
    LEVEL = int(LEVEL)

logging.basicConfig(format='%(name)s [%(levelname)s]: [%(module)s.%(funcName)s] %(message)s')

LOGGER = logging.getLogger('StreamAlert')
try:
    LOGGER.setLevel(LEVEL)
except (TypeError, ValueError) as err:
    LOGGER.setLevel('INFO')
    LOGGER.error('Defaulting to INFO logging: %s', err)

LOGGER_DEBUG_ENABLED = LOGGER.isEnabledFor(logging.DEBUG)
