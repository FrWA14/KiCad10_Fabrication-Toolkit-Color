"""Structured run report (report.json) and log setup."""
import json
import logging
import os
import time

LOGGER_NAME = "color_silkscreen"


class Report:
    def __init__(self, input_board=None, kicad_version=None):
        self.data = {
            "status": "ok",
            "kicad_version": kicad_version,
            "input_board": input_board,
            "steps": [],
            "errors": [],
            "warnings": [],
        }
        self._t0 = time.time()

    def step(self, name, ok=True, **fields):
        entry = {"name": name, "ok": ok}
        entry.update(fields)
        self.data["steps"].append(entry)
        logging.getLogger(LOGGER_NAME).info("step %s ok=%s %s", name, ok,
                                            {k: v for k, v in fields.items() if k != "files"})
        return entry

    def warn(self, warning):
        self.data["warnings"].append(warning)
        logging.getLogger(LOGGER_NAME).warning("%s %s", warning.get("code"), warning.get("message"))

    def error(self, err):
        self.data["status"] = "error"
        self.data["errors"].append(err.as_dict() if hasattr(err, "as_dict") else err)
        logging.getLogger(LOGGER_NAME).error("%s", self.data["errors"][-1])

    @property
    def ok(self):
        return self.data["status"] == "ok"

    def write(self, path):
        self.data["duration_s"] = round(time.time() - self._t0, 3)
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, ensure_ascii=False)


def setup_logging(log_path=None, console=True):
    """Log to `log_path` (and the console). Safe to call more than once."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    if log_path:
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    if console:
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    logger.propagate = False
    return logger
