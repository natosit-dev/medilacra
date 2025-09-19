# spark_delta.py
from pyspark.sql import SparkSession
from delta import configure_spark_with_delta_pip

def get_spark(app_name: str = "MediLacra", warehouse_dir: str = "./spark-warehouse"):
    builder = (
        SparkSession.builder
        .appName(app_name)
        .master("local[*]")  # all local cores
        # Delta Lake integration
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        # Local metastore/warehouse (optional, but handy if you want "tables" not just "paths")
        .config("spark.sql.warehouse.dir", warehouse_dir)
        # Reasonable local defaults
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.databricks.delta.optimizeWrite.enabled", "true")
        .config("spark.databricks.delta.autoCompact.enabled", "true")
    )
    spark = configure_spark_with_delta_pip(builder).getOrCreate()
    return spark
