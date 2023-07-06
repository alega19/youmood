import contextlib
import functools
import os
import threading

import psycopg2.extensions
import psycopg2.extras
import psycopg2.pool


DSN = os.environ["DSN"]


def register_dict_as_json():
    psycopg2.extensions.register_adapter(dict, psycopg2.extras.Json)
    psycopg2.extensions.register_adapter(list, psycopg2.extras.Json)


def use(fn):
    @functools.wraps(fn)
    def wrapper(*args, db_connection=None, **kwargs):
        if db_connection is not None:
            return fn(*args, db_connection=db_connection, **kwargs)

        with use.lock:
            if not hasattr(use, "pool"):
                use.pool = psycopg2.pool.SimpleConnectionPool(1, 5, dsn=DSN)
            connection = use.pool.getconn()
        try:
            return fn(*args, db_connection=DatabaseConnection(connection), **kwargs)
        finally:
            with use.lock:
                use.pool.putconn(connection)
    return wrapper


use.lock = threading.RLock()

Undefined = object()


class DatabaseConnection:
    def __init__(self, psycopg2_connection):
        psycopg2_connection.autocommit = True
        self._psycopg2_connection = psycopg2_connection

    @contextlib.contextmanager
    def transaction(self):
        with self._psycopg2_connection:
            yield self

    def execute(self, query, *args, **kwargs):
        with self._psycopg2_connection.cursor() as cursor:
            cursor.execute(query, *args, **kwargs)

    def executemany(self, query, params_list, page_size=100):
        if len(params_list) > page_size and self._psycopg2_connection.status != psycopg2.extensions.STATUS_IN_TRANSACTION:
            raise RuntimeError("multipage query requires transaction mode")
        with self._psycopg2_connection.cursor() as cursor:
            psycopg2.extras.execute_batch(cursor, query, params_list, page_size)

    def fetch(self, query, *args, **kwargs):
        with self._psycopg2_connection.cursor() as cursor:
            cursor.execute(query, *args, **kwargs)
            return cursor.fetchall()

    def fetchrow(self, query, *args, **kwargs):
        with self._psycopg2_connection.cursor() as cursor:
            cursor.execute(query, *args, **kwargs)
            row = cursor.fetchone()
            if row is None:
                raise EmptyResult()
            if cursor.fetchone() is not None:
                raise RuntimeError("result has multiple rows")
            return row

    def fetchval(self, query, *args, default=Undefined, **kwargs):
        with self._psycopg2_connection.cursor() as cursor:
            cursor.execute(query, *args, **kwargs)
            row = cursor.fetchone()
            if row is None:
                if default is Undefined:
                    raise EmptyResult()
                row = (default,)
            if cursor.fetchone() is not None:
                raise RuntimeError("result has multiple rows")
            if len(row) > 1:
                raise RuntimeError("result has multiple columns")
            return row[0]


class EmptyResult(Exception):
    pass
