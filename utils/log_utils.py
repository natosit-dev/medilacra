import logging
import json
import os
from datetime import datetime


class JSONFormatter(logging.Formatter):
    def format(self, record):
        record_dict = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Merge in any extra fields
        if hasattr(record, "context") and isinstance(record.context, dict):
            record_dict.update(record.context)

        return json.dumps(record_dict)


def get_logger(name="ImpleMetrix", level=logging.INFO, context=None):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    os.makedirs("logs/json", exist_ok=True)
    os.makedirs("logs/plain", exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file_plain = f"logs/plain/{name}_{date_str}.log"
    log_file_json = f"logs/json/{name}_{date_str}.json"

    # Plain text handler
    file_handler_plain = logging.FileHandler(log_file_plain)
    file_handler_plain.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler_plain)

    # JSON handler
    file_handler_json = logging.FileHandler(log_file_json)
    file_handler_json.setFormatter(JSONFormatter())
    logger.addHandler(file_handler_json)

    # Console handler (for dev)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(console_handler)

    # Add context injection to each logger method
    def _add_context(method):
        def wrapper(msg, *args, **kwargs):
            extra = kwargs.get("extra", {})
            extra["context"] = context or {}
            kwargs["extra"] = extra
            return method(msg, *args, **kwargs)
        return wrapper

    logger.info = _add_context(logger.info)
    logger.warning = _add_context(logger.warning)
    logger.error = _add_context(logger.error)
    logger.debug = _add_context(logger.debug)

    return logger
