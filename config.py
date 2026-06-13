import os
import configparser

class Section:
    pass


class Config:

    def __init__(self):
        self.cp = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))

    def _load_values(self):
        for section in self.cp.sections():
            if not hasattr(self, section):
                setattr(self, section, Section())

            section_obj = getattr(self, section)

            for key, value in self.cp.items(section):
                setattr(section_obj, key, self._convert(value))

    def load(self, filename):
        loaded = self.cp.read(filename)
        if not loaded:
            raise FileNotFoundError(filename)
        self._load_values()

    def resolve_paths(self):
        if not hasattr(self, "paths"):
            raise ValueError("[paths] section missing")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if not os.path.isabs(self.paths.yf_data_path):
            self.paths.yf_data_path = os.path.join(script_dir, self.paths.yf_data_path)
        if not os.path.isabs(self.paths.data_path):
            self.paths.data_path = os.path.join(script_dir, self.paths.data_path)
        if not os.path.isabs(self.paths.output_path):
            self.paths.output_path = os.path.join(script_dir, self.paths.output_path)

    @staticmethod
    def _convert(value):

        value = value.strip()
        if value == "":
            raise ValueError(...)

        if value.lower() in ("true", "false"):
            return value.lower() == "true"

        try:
            return int(value)
        except ValueError:
            pass

        try:
            return float(value)
        except ValueError:
            pass

        return value


gcfg = Config()
gcfg.load("config.ini")
gcfg.resolve_paths()
