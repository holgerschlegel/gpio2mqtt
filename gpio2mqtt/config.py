from dataclasses import dataclass
from datetime import datetime
from logging import Logger
from typing import Self


class ConfigParser:
    """
    Parser/helper to access the configuration dictionary.
    """

    __slots__ = ("_raw", "_logger", "_base_key", "_parent_parser", "_errors")


    def __init__(self, raw: dict[str, str], logger: Logger, base_key: str = "", parent_parser: Self = None):
        """
        Creates an instance for the root node of the given dictionary.
        The optional arguments (base_key and parent_parser) are for internal use only.

        Args:
            raw (dict[str, str]): the raw dictionary
            logger (Logger): the logger for error messages
            base_key (str, optional): the node base key
            parent_parser (Self, optional): the parent parser instance
        """
        self._raw = raw
        self._logger = logger
        self._base_key = base_key if base_key else ""
        self._parent_parser = parent_parser
        self._errors: int = 0


    def __str__(self):
        return f"ConfigParser(base_key={self._base_key}, raw={self._raw})"


    @property
    def base_key(self) -> str:
        """
        Returns:
            str: the node base key, an empty string for the root node
        """
        return self._base_key


    @property
    def has_errors(self) -> bool:
        """
        Returns:
            bool: True if this node or any sub node parser has reported an error, False otherwise
        """
        return self._errors > 0


    def get_node_parser(self, key: str, logger: Logger = None, return_empty = True) -> Self:
        """
        Creates a new parser for the sub node with the given key.

        Args:
            key (str): the key for the sub node
            logger (Logger, optional): the logger for error messages, None to use the logger of this instance
            return_empty (bool, optional):
                    True to return a parser for empty or not existing sub nodes
                    False to return None for empty or not existing sub nodes
        Returns:
            Self: the parser for the sub node, None if return_empty is False and dictionary contains no values for the sub node
        """
        node_raw = self._raw.get(key)
        if node_raw is None and return_empty:
            # node not found and should return empty
            node_raw = {}
        elif node_raw and not return_empty:
            # empty node found and should return none instead
            node_raw = None

        result: Self = None
        if node_raw is not None:
            node_logger = logger if logger is not None else self._logger
            node_base_key = (self._base_key + "." if self._base_key else "") + key + "."
            result = ConfigParser(node_raw, node_logger, node_base_key, self)
        return result


    def get_list_parsers(self, key: str, logger: Logger = None) -> list[Self]:
        # TODO doc
        list_raw = self._raw.get(key, [])
        result: list[Self] = []
        if list_raw:
            node_logger = logger if logger is not None else self._logger
            list_base_key = (self._base_key + "." if self._base_key else "") + key
            for idx, node_raw in enumerate(list_raw):
                node_base_key = list_base_key + "[" + str(idx) + "]."
                result.append(ConfigParser(node_raw, node_logger, node_base_key, self))
        return result


    def get_str(self, key: str, mandatory: bool = False, default: str = None, allowed: set[str] = None) -> str:
        # TODO doc
        value: str = self._raw.get(key, default)
        if not value:
            if mandatory:
                self.error("Mandatory value missing: %s%s", self._base_key, key)
        elif allowed is not None and value not in allowed:
            self.error("Invalid value: %s%s: %s is not in %s", self._base_key, key, value, allowed)
            value = None
        return value


    def get_bool(self, key: str, mandatory: bool = False, default: bool = None) -> bool:
        # TODO doc
        string: str = self._raw.get(key)
        value: bool = None
        if string is None:
            if default is not None:
                value = default
            elif mandatory:
                self.error("Mandatory value missing: %s%s", self._base_key, key)
        else:
            try:
                value = bool(string)
            except ValueError:
                self.error("Invalid value: %s%s: %s is not a bool", self._base_key, key, string)
        return value


    def get_int(self, key: str, mandatory: bool = False, default: int = None, min: int = None, max: int = None) -> int:
        # TODO doc
        string: str = self._raw.get(key)
        value: int = None
        if string is None:
            if default is not None:
                value = default
            elif mandatory:
                self.error("Mandatory value missing: %s%s", self._base_key, key)
        else:
            try:
                value = int(string)
            except ValueError:
                self.error("Invalid value: %s%s: %s is not an int", self._base_key, key, string)
            if value is not None:
                if min is not None and value < min:
                    self._critical("Invalid value: %s%s: %d is less than %d", self._base_key, key, value, min)
                if max is not None and value > max:
                    self._critical("Invalid value: %s%s: %d is greater than %d", self._base_key, key, value, max)
        return value


    def get_isodatetime(self, key: str, mandatory: bool = False, default: datetime = None) -> datetime:
        # TODO doc
        string: str = self._raw.get(key)
        value: datetime = None
        if string is None:
            if default is not None:
                value = default
            elif mandatory:
                self.error("Mandatory value missing: %s%s", self._base_key, key)
        else:
            try:
                value = datetime.fromisoformat(string)
            except ValueError:
                self.error("Invalid value: %s%s: %s is not a datetime", self._base_key, key, string)
        return value


    def check_unique(self, key: str, value: any, values: set[any]) -> bool:
        # TODO doc
        result: bool = value not in values
        if result:
            values.add(value)
        else:
            self.error("Duplicate value: %s%s: %s", self._base_key, key, value)
        return result


    def error(self, msg, *args) -> None:
        """
        Logs the given error message, if the logger of this instance is created with a logger.
        Sets the errors flag of this instance and recursively in all parent instances, if any.

        Args:
            msg (_type_): the error message
        """
        if self._logger:
            self._logger.critical(msg, *args)
        self._inc_errors()


    def _inc_errors(self) -> None:
        self._errors += 1
        if self._parent_parser:
            self._parent_parser._inc_errors()
