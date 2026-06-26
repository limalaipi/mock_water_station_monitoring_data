from impala.dbapi import connect
import pandas as pd


class ImpalaInstance():

    def __init__(self, config):
        self.conn = None
        self.cur = None
        self.config = config
        self.host = config['host']
        self.port = config.get('port', 21050)
        self.user = config.get('user', None)
        self.database = config.get('database', 'default')

    def get_dbinstance(self):
        return self.conn, self.cur

    def connect(self):
        '''Get connection and return connection + cursor'''
        try:
            print('Initial connector')
            self.conn = connect(
                host=self.host,
                port=self.port,
                user=self.user,
                database=self.database
            )
            print('Impala connected')
            self.cur = self.conn.cursor()
            self.cur.execute('SELECT VERSION()')
            res = self.cur.fetchone()
            print('Impala version:', res)
            return self
        except Exception as E:
            print('Error >>', E)

    def query(self, query_string, close=True):
        try:
            self.cur.execute(query_string)
            columns = [desc[0] for desc in self.cur.description]
            buffer = []
            for row in self.cur:
                buffer.append(dict(zip(columns, row)))
            if close:
                self.close_connection()
            return {"data": buffer}
        except Exception as err:
            print(err)
            self.close_connection()

    def close_connection(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        print('Connection closed')

    def insert_data(self, df, table, schema):
        chunk_size = 1000
        
        # Identify column types from DataFrame
        numeric_cols = set(df.select_dtypes(include=['number']).columns)
        datetime_cols = set(df.select_dtypes(include=['datetime64']).columns)
        
        for chunk_start in range(0, len(df), chunk_size):
            chunk_end = min(chunk_start + chunk_size, len(df))
            chunk_df = df.iloc[chunk_start:chunk_end]

            for _, row in chunk_df.iterrows():
                columns = ', '.join(df.columns)
                value_list = []
                for col in df.columns:
                    val = row[col]
                    if val is None or pd.isnull(val):
                        value_list.append('NULL')
                    elif col in numeric_cols:
                        value_list.append(str(val))
                    elif col in datetime_cols:
                        value_list.append(f"'{val}'")
                    else:
                        val_str = str(val).replace("'", "''")
                        value_list.append(f"'{val_str}'")

                values = ', '.join(value_list)
                query_insert = f"INSERT INTO {schema}.{table} ({columns}) VALUES ({values})"
                self.cur.execute(query_insert)

    def truncate_table(self, table, schema):
        try:
            query = f"TRUNCATE TABLE {schema}.{table}"
            self.cur.execute(query)
            print(f"Table {schema}.{table} truncated successfully")
        except Exception as err:
            print(f"Error truncating table: {err}")
            raise