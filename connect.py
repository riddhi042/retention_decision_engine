import os
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

url = URL.create("postgresql+psycopg2", username="postgres",
                 password=os.environ["PGPASSWORD"], host="localhost",
                 port=5432, database="churn")
engine = create_engine(url)

df = pd.read_sql("SELECT * FROM customer_status", engine)
print(df.shape)
print(df.head())