#config.py

AIRNOW_API_KEY = "86B0C1FD-C0D8-4A01-BA10-C04A0B718B6C"
AIRNOW_MILES_DEFAULT = 75
ACS_YEAR = "2022"  # update when 2023 5-yr is available

def configure_logging():
    import logging
    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(levelname)s: %(message)s')
    logging.getLogger("urllib3").setLevel(logging.DEBUG)
