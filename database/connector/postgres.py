from psycopg2 import connect
import psycopg2
from psycopg2.extras import RealDictCursor,DictCursor
# from app.common.config import ConfigService
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from urllib.parse import quote_plus
import pandas as pd
from psycopg2 import sql
from psycopg2.extras import execute_values




class PostGresInstance():
    
    def __init__(self,config):
        self.conn = None
        self.cur = None
        self.engine = None
        self.config = config
        self.user = self.config['user']
        self.host = config['host']
        self.database = self.config['database']
        self.password = self.config['password']

        # self.config_pg = ConfigService.spatial_config(self)
        # print("configggg",config)
        # print("aaaa",self.config_pg)

    def get_dbinstance(self):
            return self.conn,self.cur
    def get_url(self):
        return f'postgresql://{self.user}:%s@{self.host}/{self.database}' % quote_plus(self.password)
    def get_engine(self):
        url = self.get_url()
        return create_engine(url)
    def get_session(self):
        "setup per test.  create a new Session."
        session = Session(self.get_engine())
        # pre-connect so this part isn't profiled (if we choose)
        session.connection()
        return session
    # def get_orm_con(self):


    def connect(self):
        '''Get connection and return connection + cursor'''
        try:
            print('Initial connector')
            self.conn = connect(**self.config)
            print('Postgres connected')
            self.cur = self.conn.cursor(cursor_factory=DictCursor)
            res = self.query('select version()',False)
            # print(res['data'])
            return self
        except Exception as E:
            print('Error >>',E)
            # raise HTTPException(status_code=500, detail="Can't connect to database server.")
        
    def query(self,query_string,close=True):
        try:
            jsonKey=[]
            buffer=[]
            self.cur.execute(query_string)
            description = self.cur.description
            for i in description:
                jsonKey.append(i[0])
            
            for element in self.cur :
                # print(element) 
                buffer.append(dict(zip(jsonKey, element)))
            if close:
                self.close_connection()
            return {"data":buffer}
        except Exception as err:
            print(err)
            self.close_connection()
            # raise HTTPException(status_code=500, detail=str(err))
    
    def switch_database(self,dbName:str):
        # print("aaaa",self.config["PG_HOST"])
        try:
            # self.close_connection()
            self.pg_conn = psycopg2.connect(
                    host=self.config_pg["PG_HOST"],
                    port=self.config_pg["PG_PORT"],
                    database=dbName,
                    user=self.config_pg['PG_USER'],
                    password=self.config_pg["PG_PASS"]
                )   
            self.pg_conn.set_session(autocommit=True)
            pg_curr = self.pg_conn.cursor()
            # print("Connected to PostgreSQL server!")
            return self.pg_conn, pg_curr
        except psycopg2.Error:
            pass
            # raise HTTPException(status_code=500, detail="Can't connect to database server.")



    
    def dataframe(self,query_string,close=True):
        try:
            jsonKey=[]
            buffer=[]
            self.cur.execute(query_string)
            description = self.cur.description
            for i in description:
                jsonKey.append(i[0])
            
            for element in self.cur :
                # print(element) 
                buffer.append(dict(zip(jsonKey, element)))
            if close:
                self.close_connection()
            return pd.DataFrame(buffer,columns=jsonKey)
        except Exception as err:
            print(err)
            # raise HTTPException(status_code=500, detail=str(err))
        
    def close_connection(self):
        if(self.conn):
            self.conn.close()
        print('Connection closed')


    def insert_data(self,df, table, schema,constraint=None):
        chunk_size = 1000
        constraint_ = f' ON CONFLICT ON CONSTRAINT {constraint} DO NOTHING;'
        for chunk_start in range(0, len(df), chunk_size):
            chunk_end = min(chunk_start + chunk_size, len(df))
            chunk_df = df.iloc[chunk_start:chunk_end]
            
            for _, row in chunk_df.iterrows():
                columns = ', '.join(df.columns)
                values = ', '.join([f"'{row[col]}'" if pd.notnull(row[col]) else 'NULL' for col in df.columns])
                query_insert = f"INSERT INTO {schema}.{table} ({columns}) VALUES ({values}) "
                if constraint:
                    query_insert += constraint_
                self.cur.execute(query_insert)
                self.conn.commit()
    
    def upsert_data(self, df, table, schema, conflict_cols=None, constraint=None, update_cols=None):
   
        if df is None or df.empty:
            return

        if not conflict_cols and not constraint:
            raise ValueError("ต้องระบุ conflict_cols หรือ constraint อย่างใดอย่างหนึ่งสำหรับ upsert")

        chunk_size = 1000

        cols = list(df.columns)

        if update_cols is None:
            if conflict_cols:
                update_cols = [c for c in cols if c not in conflict_cols]
            else:
                update_cols = cols

        insert_cols_sql = sql.SQL(", ").join(map(sql.Identifier, cols))

        if constraint:
            conflict_sql = sql.SQL("ON CONFLICT ON CONSTRAINT {}").format(sql.Identifier(constraint))
        else:
            conflict_sql = sql.SQL("ON CONFLICT ({})").format(
                sql.SQL(", ").join(map(sql.Identifier, conflict_cols))
            )

        update_sql = sql.SQL(", ").join(
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c))
            for c in update_cols
        )

        base_query = sql.SQL("""
            INSERT INTO {}.{} ({})
            VALUES %s
            {}
            DO UPDATE SET {}
        """).format(
            sql.Identifier(schema),
            sql.Identifier(table),
            insert_cols_sql,
            conflict_sql,
            update_sql
        )

        for start in range(0, len(df), chunk_size):
            end = min(start + chunk_size, len(df))
            chunk_df = df.iloc[start:end]

            # แปลงเป็น list of tuples
            values = [tuple(None if pd.isna(x) else x for x in row) for row in chunk_df.to_numpy()]

            execute_values(self.cur, base_query, values, page_size=chunk_size)
            self.conn.commit()

    def update_data(self, df, table, schema, key_columns):
        # Fetch column names from the database
        self.cur.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
        """, (schema, table))
        table_columns = [r[0] for r in self.cur.fetchall()]

        # Filter DataFrame to include only columns present in the table
        df = df[[c for c in df.columns if c in table_columns]]

        chunk_size = 1000
        for chunk_start in range(0, len(df), chunk_size):
            chunk_end = min(chunk_start + chunk_size, len(df))
            chunk_df = df.iloc[chunk_start:chunk_end]

            for _, row in chunk_df.iterrows():
                set_clauses = []
                where_clauses = []
                for col in df.columns:
                    value = f"'{row[col]}'" if pd.notnull(row[col]) else 'NULL'
                    if col in key_columns:
                        where_clauses.append(f"{col} = {value}")
                    else:
                        set_clauses.append(f"{col} = {value}")

                if not set_clauses:  # skip if no columns to update
                    continue

                query_update = f"""
                    UPDATE {schema}.{table}
                    SET {', '.join(set_clauses)}
                    WHERE {' AND '.join(where_clauses)};
                """
                self.cur.execute(query_update)
            self.conn.commit()

    def truncate_table(self, table, schema, cascade=False, restart_identity=False):
        """
        Truncate a table in the specified schema.
        
        Args:
            table: Table name to truncate
            schema: Schema name
            cascade: If True, automatically truncate all tables that have foreign-key references
            restart_identity: If True, reset any associated sequences
        """
        try:
            options = []
            if restart_identity:
                options.append("RESTART IDENTITY")
            if cascade:
                options.append("CASCADE")
            
            options_sql = " ".join(options)
            
            query = sql.SQL("TRUNCATE TABLE {}.{} {}").format(
                sql.Identifier(schema),
                sql.Identifier(table),
                sql.SQL(options_sql)
            )
            
            self.cur.execute(query)
            self.conn.commit()
            print(f"Table {schema}.{table} truncated successfully")
        except Exception as err:
            print(f"Error truncating table: {err}")
            self.conn.rollback()
            raise