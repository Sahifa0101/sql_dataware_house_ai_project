/*
===============================================================================
Loading the raw data into bronze layer
===============================================================================
Script Purpose:
    the below python script is used to load the raw data into bronze layer with
    out writing any sql commands 
===============================================================================
*/

import os
import math
import pandas as pd
import pyodbc


# ============================================================
# 1. SQL SERVER CONNECTION
# ============================================================

server = "DESKTOP-RGB1F65"
database = "DataWarehouse"

connection_string = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={server};"
    f"DATABASE={database};"
    "Trusted_Connection=yes;"
)

conn = pyodbc.connect(connection_string)

print("=" * 70)
print("SQL SERVER CONNECTION SUCCESSFUL")
print("=" * 70)


# ============================================================
# 2. BASE SOURCE PATH
# ============================================================

base_path = (
    r"C:\Users\Lenovo\Downloads"
    r"\sql-data-warehouse-project-main"
    r"\sql-data-warehouse-project-main"
    r"\datasets"
)


# ============================================================
# 3. SIX SOURCE FILES
# ============================================================

sources = [

    {
        "name": "CRM Customer",
        "file": os.path.join(
            base_path,
            "source_crm",
            "cust_info.csv"
        ),
        "table": "bronze.crm_cust_info"
    },

    {
        "name": "CRM Product",
        "file": os.path.join(
            base_path,
            "source_crm",
            "prd_info.csv"
        ),
        "table": "bronze.crm_prd_info"
    },

    {
        "name": "CRM Sales",
        "file": os.path.join(
            base_path,
            "source_crm",
            "sales_details.csv"
        ),
        "table": "bronze.crm_sales_details"
    },

    {
        "name": "ERP Customer",
        "file": os.path.join(
            base_path,
            "source_erp",
            "CUST_AZ12.csv"
        ),
        "table": "bronze.erp_cust_az12"
    },

    {
        "name": "ERP Location",
        "file": os.path.join(
            base_path,
            "source_erp",
            "LOC_A101.csv"
        ),
        "table": "bronze.erp_loc_a101"
    },

    {
        "name": "ERP Category",
        "file": os.path.join(
            base_path,
            "source_erp",
            "PX_CAT_G1V2.csv"
        ),
        "table": "bronze.erp_px_cat_g1v2"
    }

]


# ============================================================
# 4. GET SQL SERVER COLUMN INFORMATION
# ============================================================

def get_sql_columns(cursor, table_name):

    schema_name, table_only = table_name.split(".")

    query = """
    SELECT
        COLUMN_NAME,
        DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = ?
      AND TABLE_NAME = ?
    ORDER BY ORDINAL_POSITION
    """

    cursor.execute(
        query,
        schema_name,
        table_only
    )

    rows = cursor.fetchall()

    if not rows:
        raise Exception(
            f"Target table not found: {table_name}"
        )

    return {
        row.COLUMN_NAME.lower(): row.DATA_TYPE.lower()
        for row in rows
    }


# ============================================================
# 5. CLEAN VALUE BASED ON SQL DATATYPE
# ============================================================

def clean_value(value, sql_type):

    # --------------------------------------------------------
    # Missing values
    # --------------------------------------------------------

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass


    # --------------------------------------------------------
    # INTEGER TYPES
    # --------------------------------------------------------

    if sql_type in (
        "int",
        "bigint",
        "smallint",
        "tinyint"
    ):

        try:
            return int(float(value))

        except (ValueError, TypeError):
            return None


    # --------------------------------------------------------
    # NUMERIC / FLOAT TYPES
    # --------------------------------------------------------

    if sql_type in (
        "decimal",
        "numeric",
        "float",
        "real",
        "money",
        "smallmoney"
    ):

        try:

            numeric_value = float(value)

            if math.isnan(numeric_value):
                return None

            if math.isinf(numeric_value):
                return None

            return numeric_value

        except (ValueError, TypeError):
            return None


    # --------------------------------------------------------
    # DATE / DATETIME TYPES
    # --------------------------------------------------------

    if sql_type in (
        "date",
        "datetime",
        "datetime2",
        "smalldatetime",
        "datetimeoffset"
    ):

        try:

            converted_date = pd.to_datetime(
                value,
                errors="coerce"
            )

            if pd.isna(converted_date):
                return None

            return converted_date.to_pydatetime()

        except (ValueError, TypeError):
            return None


    # --------------------------------------------------------
    # BIT
    # --------------------------------------------------------

    if sql_type == "bit":

        value_string = str(value).strip().lower()

        if value_string in (
            "true",
            "1",
            "yes"
        ):
            return 1

        if value_string in (
            "false",
            "0",
            "no"
        ):
            return 0

        return None


    # --------------------------------------------------------
    # STRING TYPES
    # --------------------------------------------------------

    if sql_type in (
        "varchar",
        "nvarchar",
        "char",
        "nchar",
        "text",
        "ntext"
    ):

        return str(value).strip()


    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    return value


# ============================================================
# 6. LOAD ONE SOURCE
# ============================================================

def load_source(cursor, source):

    source_name = source["name"]
    file_path = source["file"]
    table_name = source["table"]


    print("\n")
    print("=" * 70)
    print(f"STARTING: {source_name}")
    print("=" * 70)

    print(f"Source : {file_path}")
    print(f"Target : {table_name}")


    # ========================================================
    # CHECK FILE
    # ========================================================

    if not os.path.exists(file_path):

        raise FileNotFoundError(
            f"\nCSV file not found:\n{file_path}"
        )


    # ========================================================
    # READ CSV
    # ========================================================

    print("\nReading CSV...")

    df = pd.read_csv(file_path)

    print(
        f"CSV loaded successfully - "
        f"{len(df)} records"
    )

    print("\nOriginal CSV columns:")
    print(df.columns.tolist())


    # ========================================================
    # NORMALIZE COLUMN NAMES
    # ========================================================

    # IMPORTANT FIX:
    #
    # CID   -> cid
    # BDATE -> bdate
    # GEN   -> gen
    #
    # Also removes leading/trailing spaces.

    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
    )

    print("\nNormalized CSV columns:")
    print(df.columns.tolist())


    # ========================================================
    # GET SQL SERVER COLUMN DEFINITIONS
    # ========================================================

    sql_columns = get_sql_columns(
        cursor,
        table_name
    )

    print("\nSQL Server target columns:")
    print(list(sql_columns.keys()))


    # ========================================================
    # SOURCE COLUMNS
    # ========================================================

    source_columns = list(df.columns)


    # ========================================================
    # CHECK FOR MISSING TARGET COLUMNS
    # ========================================================

    missing_columns = [
        column
        for column in sql_columns
        if column not in source_columns
    ]


    # ========================================================
    # CHECK FOR EXTRA SOURCE COLUMNS
    # ========================================================

    extra_columns = [
        column
        for column in source_columns
        if column not in sql_columns
    ]


    if missing_columns:

        raise Exception(
            f"\nMissing columns in CSV for "
            f"{table_name}: {missing_columns}"
        )


    if extra_columns:

        print(
            "\nWarning - Extra CSV columns ignored:"
        )

        print(extra_columns)


    # ========================================================
    # KEEP SQL TARGET COLUMN ORDER
    # ========================================================

    target_columns = list(
        sql_columns.keys()
    )

    df = df[target_columns]


    # ========================================================
    # CLEAN DATA
    # ========================================================

    print("\nCleaning data...")

    for column in target_columns:

        sql_type = sql_columns[column]

        df[column] = df[column].apply(
            lambda value: clean_value(
                value,
                sql_type
            )
        )


    print("Data cleaning completed.")


    # ========================================================
    # FINAL NaN / NaT PROTECTION
    # ========================================================

    for column in target_columns:

        df[column] = df[column].apply(
            lambda value:
            None
            if pd.isna(value)
            else value
        )


    # ========================================================
    # TRUNCATE TARGET TABLE
    # ========================================================

    print(
        f"\nTruncating {table_name}..."
    )

    cursor.execute(
        f"TRUNCATE TABLE {table_name}"
    )

    print("Table truncated successfully.")


    # ========================================================
    # BUILD INSERT QUERY
    # ========================================================

    column_list = ", ".join(
        f"[{column}]"
        for column in target_columns
    )

    placeholders = ", ".join(
        "?"
        for _ in target_columns
    )

    insert_query = f"""
    INSERT INTO {table_name}
    (
        {column_list}
    )
    VALUES
    (
        {placeholders}
    )
    """


    # ========================================================
    # INSERT DATA
    # ========================================================

    print(
        f"\nLoading {len(df)} records..."
    )

    success_count = 0


    for row_number, row in enumerate(
        df.itertuples(
            index=False,
            name=None
        ),
        start=1
    ):

        # ----------------------------------------------------
        # FINAL PYTHON VALUE CLEANING
        # ----------------------------------------------------

        cleaned_row = []

        for value in row:

            try:

                if pd.isna(value):

                    cleaned_row.append(None)

                elif (
                    isinstance(value, float)
                    and math.isnan(value)
                ):

                    cleaned_row.append(None)

                else:

                    cleaned_row.append(value)

            except (TypeError, ValueError):

                cleaned_row.append(value)


        cleaned_row = tuple(
            cleaned_row
        )


        # ----------------------------------------------------
        # INSERT
        # ----------------------------------------------------

        try:

            cursor.execute(
                insert_query,
                cleaned_row
            )

            success_count += 1


        except pyodbc.Error as e:

            print("\n")
            print("=" * 70)
            print("ERROR WHILE INSERTING DATA")
            print("=" * 70)

            print(
                f"Source     : {source_name}"
            )

            print(
                f"Table      : {table_name}"
            )

            print(
                f"Row number : {row_number}"
            )

            print(
                f"Row        : {cleaned_row}"
            )

            print("\nSQL Server Error:")
            print(e)

            raise


    # ========================================================
    # COMMIT
    # ========================================================

    conn.commit()


    # ========================================================
    # VERIFY
    # ========================================================

    cursor.execute(
        f"SELECT COUNT(*) FROM {table_name}"
    )

    loaded_count = cursor.fetchone()[0]


    # ========================================================
    # RESULT
    # ========================================================

    print("\n")
    print("-" * 70)
    print(f"{source_name} LOAD COMPLETED")
    print("-" * 70)

    print(
        f"CSV records       : {len(df)}"
    )

    print(
        f"Python inserts    : {success_count}"
    )

    print(
        f"SQL table records : {loaded_count}"
    )


    if loaded_count == len(df):

        print(
            "STATUS            : SUCCESS"
        )

    else:

        print(
            "STATUS            : WARNING - "
            "COUNT MISMATCH"
        )


# ============================================================
# 7. MAIN PROGRAM
# ============================================================

cursor = conn.cursor()


try:

    # --------------------------------------------------------
    # Process all six sources
    # --------------------------------------------------------

    for source in sources:

        load_source(
            cursor,
            source
        )


    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print("\n\n")
    print("=" * 70)
    print("ALL 6 BRONZE SOURCES PROCESSED")
    print("=" * 70)

    print("\nBronze tables loaded:")

    for source in sources:

        table_name = source["table"]

        cursor.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        )

        count = cursor.fetchone()[0]

        print(
            f"{table_name:<35} : {count} records"
        )


    print("\n")
    print("=" * 70)
    print("BRONZE LOAD COMPLETED SUCCESSFULLY")
    print("=" * 70)


except Exception as e:

    print("\n")
    print("=" * 70)
    print("BRONZE LOAD FAILED")
    print("=" * 70)

    print(e)

    conn.rollback()

    raise


finally:

    cursor.close()
    conn.close()

    print("\nSQL Server connection closed.")
