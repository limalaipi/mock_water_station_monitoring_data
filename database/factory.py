# database/factory.py
"""
ConnectionFactory
=================
Maps a db_type string to the correct adapter class and instantiates it.
This is the ONLY place that imports concrete adapter modules.
All other code imports only this factory.

Adapters are imported lazily — only the requested db_type's module is
loaded. This keeps startup fast and avoids requiring every DB driver
(oracledb, jaydebeapi/jpype, impyla, ...) to be installed just to run
against a single database.

Usage:
    from database.factory import ConnectionFactory
    adapter = ConnectionFactory.get("postgresql", config_dict)
"""

from importlib import import_module

# Registry: maps driver name → (module path, adapter class name).
# The module is imported only when that db_type is actually requested.
_REGISTRY = {
    "postgresql": ("database.adapters.postgres", "PostgresAdapter"),
    "impala":     ("database.adapters.impala",   "ImpalaAdapter"),
    "hive":       ("database.adapters.hive",     "HiveAdapter"),
    "mysql":      ("database.adapters.mysql",    "MySQLAdapter"),
    "oracle":     ("database.adapters.oracle",   "OracleAdapter"),
    "mssql":      ("database.adapters.mssql",    "MSSQLAdapter"),
    "db2":        ("database.adapters.db2",      "Db2Adapter"),
}


class ConnectionFactory:

    @staticmethod
    def get(db_type: str, config: dict):
        """
        Instantiate and return an adapter for the given db_type.

        The adapter module is imported lazily on first use, so only the
        driver for the requested database needs to be installed.

        Args:
            db_type: One of the keys in _REGISTRY (e.g. "postgresql", "hive").
            config:  Dict of connection parameters (host, port, database, etc.)
                     resolved from connections.yaml + .env.

        Returns:
            A concrete BaseAdapter subclass instance (not yet connected).

        Raises:
            ValueError: If db_type is not registered.
        """
        key = db_type.lower()
        if key not in _REGISTRY:
            supported = ", ".join(_REGISTRY.keys())
            raise ValueError(
                f"Unknown db_type '{db_type}'. Supported: {supported}"
            )
        module_path, class_name = _REGISTRY[key]
        adapter_class = getattr(import_module(module_path), class_name)
        return adapter_class(config)

    @staticmethod
    def supported() -> list:
        """Return list of all registered db_type names."""
        return list(_REGISTRY.keys())
