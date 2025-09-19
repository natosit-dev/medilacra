# storage_delta.py
from datetime import datetime, date
from typing import Iterable, Mapping
from pyspark.sql import Row, functions as F
from spark_delta import get_spark

# Root folder for all Delta tables (override in get_spark if you prefer)
ROOT = "./deltalake"

def _path(*parts):  # join helper
    import os
    return "/".join([p.strip("/\\") for p in parts])

def append_bronze_messages(rows: Iterable[Mapping], root: str = ROOT):
    """
    rows: iterable of dicts with keys:
      run_id, message_type, control_id, encounter_id, raw_hl7, written_path, ingest_ts (datetime)
    """
    spark = get_spark()
    df = spark.createDataFrame([Row(**r) for r in rows])
    df = df.withColumn("dt", F.to_date(F.col("ingest_ts")))
    (df.write
       .format("delta")
       .mode("append")
       .partitionBy("dt")
       .save(_path(root, "bronze", "messages")))
    return df.count()

def read_bronze_messages(root: str = ROOT):
    spark = get_spark()
    return spark.read.format("delta").load(_path(root, "bronze", "messages"))
