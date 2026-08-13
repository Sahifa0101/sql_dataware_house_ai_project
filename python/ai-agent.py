
===============================================================================
Ai Agent for quality after the transformation
===============================================================================
Script Purpose:
   This script is used to check all the transformations in the silver layer 
   whether they align with bussiness rules.
	
===============================================================================



import os
import pyodbc
from openai import OpenAI


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


# ============================================================
# 2. ALLOWED NULL COLUMNS
# ============================================================
# NULL values in these columns are allowed according to
# the current Silver-layer business rules.
# ============================================================

ALLOWED_NULLS = {

    "crm_cust_info": [],

    "crm_prd_info": [
        "prd_end_dt"
    ],

    "crm_sales_details": [
        "sls_order_dt"
    ],

    "erp_cust_az12": [
        "bdate"
    ],

    "erp_loc_a101": [],

    "erp_px_cat_g1v2": []
}


# ============================================================
# 3. BUSINESS KEYS
# ============================================================
# These keys are used by the deterministic Python DQ engine
# to check duplicate business records.
# ============================================================

BUSINESS_KEYS = {

    "crm_cust_info": [
        "cst_id"
    ],

    "crm_prd_info": [
        "prd_key"
    ],

    "crm_sales_details": [
        "sls_ord_num",
        "sls_prd_key"
    ],

    "erp_cust_az12": [
        "cid"
    ],

    "erp_loc_a101": [
        "cid"
    ],

    "erp_px_cat_g1v2": [
        "id"
    ]
}


# ============================================================
# 4. BUSINESS RULES
# ============================================================
# These rules provide business context to the AI agent.
#
# IMPORTANT:
# Python remains responsible for performing the actual
# validation. The LLM uses these rules to interpret the
# validation results.
# ============================================================

BUSINESS_RULES = {

    "silver.crm_cust_info": {

        "business_key": [
            "cst_id"
        ],

        "allowed_nulls": [],

        "rules": [
            "cst_id is the business key for the customer.",
            "Customer records should be unique by cst_id.",
            "Customer records with a NULL cst_id are not valid."
        ]
    },


    "silver.crm_prd_info": {

        "business_key": [
            "prd_key"
        ],

        "allowed_nulls": [
            "prd_end_dt"
        ],

        "rules": [
            "prd_key identifies the product.",
            "prd_end_dt can be NULL for an active product.",
            "NULL values in prd_end_dt should not automatically "
            "be treated as a data-quality failure.",
            "Product records should be evaluated according to "
            "the product business key."
        ]
    },


    "silver.crm_sales_details": {

        "business_key": [
            "sls_ord_num",
            "sls_prd_key"
        ],

        "allowed_nulls": [
            "sls_order_dt"
        ],

        "rules": [
            "A sales order can contain multiple products.",
            "sls_ord_num alone should not be considered a "
            "unique sales-detail business key.",
            "The sales-detail grain is represented by the "
            "combination of order number and product key.",
            "NULL values in sls_order_dt are allowed according "
            "to the current business rule.",
            "Duplicate checks should be evaluated at the "
            "sales-detail grain."
        ]
    },


    "silver.erp_cust_az12": {

        "business_key": [
            "cid"
        ],

        "allowed_nulls": [
            "bdate"
        ],

        "rules": [
            "cid identifies the customer in the ERP customer data.",
            "bdate can be NULL.",
            "NULL values in bdate should not automatically be "
            "treated as a data-quality failure.",
            "Customer records should be evaluated using cid "
            "as the business key."
        ]
    },


    "silver.erp_loc_a101": {

        "business_key": [
            "cid"
        ],

        "allowed_nulls": [],

        "rules": [
            "cid identifies the customer/location record.",
            "Duplicate cid values should be investigated."
        ]
    },


    "silver.erp_px_cat_g1v2": {

        "business_key": [
            "id"
        ],

        "allowed_nulls": [],

        "rules": [
            "id identifies the category/product mapping.",
            "Duplicate id values should be investigated.",
            "Required category mapping fields should not contain "
            "unexpected NULL values."
        ]
    }
}


# ============================================================
# 5. CONNECT TO SQL SERVER
# ============================================================

try:

    conn = pyodbc.connect(connection_string)

    print("=" * 70)
    print("AI DATA QUALITY AGENT")
    print("=" * 70)

    print("\nSQL Server connection successful!")

except pyodbc.Error as e:

    print("\nSQL Server connection failed!")
    print(e)

    raise


cursor = conn.cursor()


# ============================================================
# 6. GET SILVER TABLES
# ============================================================

print("\nChecking Silver schema...")

cursor.execute("""
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'silver'
    ORDER BY TABLE_NAME
""")

silver_tables = cursor.fetchall()


if not silver_tables:

    print("\nNo Silver tables found.")

    cursor.close()
    conn.close()

    raise SystemExit


print("\nSilver tables found:")

for table in silver_tables:

    print(f"- silver.{table.TABLE_NAME}")


# ============================================================
# 7. DATA QUALITY CHECK FUNCTION
# ============================================================

def check_table_quality(cursor, table_name):

    full_table_name = f"silver.{table_name}"

    print("\n")
    print("=" * 70)
    print(f"DATA QUALITY CHECK: {full_table_name}")
    print("=" * 70)


    # ========================================================
    # CHECK 1 - TOTAL ROW COUNT
    # ========================================================

    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM {full_table_name}
        """
    )

    total_rows = cursor.fetchone()[0]

    print(f"\nTotal Records: {total_rows}")


    # ========================================================
    # CHECK 2 - EMPTY TABLE
    # ========================================================

    if total_rows == 0:

        print("\nStatus: FAILED")

        print(
            "Reason: Silver table contains no records."
        )

        return {
            "table": full_table_name,
            "rows": total_rows,
            "unexpected_nulls": 0,
            "allowed_nulls": 0,
            "duplicate_keys": 0,
            "status": "FAILED"
        }


    # ========================================================
    # CHECK 3 - GET TABLE COLUMNS
    # ========================================================

    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'silver'
          AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION
        """,
        table_name
    )

    columns = cursor.fetchall()

    column_names = [
        column.COLUMN_NAME
        for column in columns
    ]


    # ========================================================
    # CHECK 4 - NULL VALUE CHECK
    # ========================================================

    print("\nNULL Value Check:")

    allowed_null_count = 0
    unexpected_null_count = 0

    for column_name in column_names:

        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM {full_table_name}
            WHERE [{column_name}] IS NULL
            """
        )

        null_count = cursor.fetchone()[0]


        if null_count == 0:
            continue


        percentage = (
            null_count / total_rows
        ) * 100


        # ----------------------------------------------------
        # Check whether NULL is allowed
        # ----------------------------------------------------

        if column_name in ALLOWED_NULLS.get(
            table_name,
            []
        ):

            allowed_null_count += null_count

            print(
                f"  {column_name}: "
                f"{null_count} NULL "
                f"({percentage:.2f}%) "
                f"→ ALLOWED / PASS"
            )

        else:

            unexpected_null_count += null_count

            print(
                f"  {column_name}: "
                f"{null_count} NULL "
                f"({percentage:.2f}%) "
                f"→ UNEXPECTED / WARNING"
            )


    if (
        allowed_null_count == 0
        and unexpected_null_count == 0
    ):

        print("  No NULL values found.")


    # ========================================================
    # CHECK 5 - BUSINESS KEY DUPLICATE CHECK
    # ========================================================

    print("\nBusiness Key Duplicate Check:")

    business_keys = BUSINESS_KEYS.get(
        table_name,
        []
    )

    duplicate_keys = 0


    if not business_keys:

        print(
            "  No business key configured."
        )

    else:

        key_list = ", ".join(
            f"[{key}]"
            for key in business_keys
        )


        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM
            (
                SELECT
                    {key_list}
                FROM {full_table_name}
                GROUP BY
                    {key_list}
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
            """
        )


        duplicate_keys = cursor.fetchone()[0]


        if duplicate_keys > 0:

            print(
                f"  Duplicate business keys: "
                f"{duplicate_keys}"
            )

        else:

            print(
                "  No duplicate business keys found."
            )


    # ========================================================
    # CHECK 6 - FINAL STATUS
    # ========================================================

    if duplicate_keys > 0:

        status = "WARNING"

    elif unexpected_null_count > 0:

        status = "WARNING"

    else:

        status = "PASS"


    print("\nOverall Table Status:")
    print(f"  {status}")


    # ========================================================
    # RETURN STRUCTURED RESULTS
    # ========================================================

    return {

        "table": full_table_name,

        "rows": total_rows,

        "unexpected_nulls":
            unexpected_null_count,

        "allowed_nulls":
            allowed_null_count,

        "duplicate_keys":
            duplicate_keys,

        "status":
            status
    }


# ============================================================
# 8. RUN DATA QUALITY CHECKS
# ============================================================

quality_results = []


for table in silver_tables:

    table_name = table.TABLE_NAME

    result = check_table_quality(
        cursor,
        table_name
    )

    quality_results.append(result)


# ============================================================
# 9. CALCULATE PIPELINE STATUS
# ============================================================

failed_tables = [

    result
    for result in quality_results
    if result["status"] == "FAILED"

]


warning_tables = [

    result
    for result in quality_results
    if result["status"] == "WARNING"

]


passed_tables = [

    result
    for result in quality_results
    if result["status"] == "PASS"

]


if failed_tables:

    overall_status = "FAILED"

elif warning_tables:

    overall_status = "WARNING"

else:

    overall_status = "PASS"


# ============================================================
# 10. DISPLAY DATA QUALITY SUMMARY
# ============================================================

print("\n\n")

print("=" * 70)
print("SILVER DATA QUALITY SUMMARY")
print("=" * 70)


for result in quality_results:

    print(
        f"\nTable            : "
        f"{result['table']}"
    )

    print(
        f"Rows             : "
        f"{result['rows']}"
    )

    print(
        f"Unexpected NULLs : "
        f"{result['unexpected_nulls']}"
    )

    print(
        f"Allowed NULLs    : "
        f"{result['allowed_nulls']}"
    )

    print(
        f"Duplicate Keys   : "
        f"{result['duplicate_keys']}"
    )

    print(
        f"Status           : "
        f"{result['status']}"
    )


# ============================================================
# 11. OVERALL PIPELINE STATUS
# ============================================================

print("\n")

print("=" * 70)
print("OVERALL PIPELINE STATUS")
print("=" * 70)


print(
    f"STATUS: {overall_status}"
)

print(
    f"\nTables checked : "
    f"{len(quality_results)}"
)

print(
    f"Passed tables  : "
    f"{len(passed_tables)}"
)

print(
    f"Warning tables : "
    f"{len(warning_tables)}"
)

print(
    f"Failed tables  : "
    f"{len(failed_tables)}"
)


# ============================================================
# 12. PREPARE BUSINESS RULES FOR AI
# ============================================================

def prepare_business_rules():

    business_rules_text = ""

    for table_name, table_rules in BUSINESS_RULES.items():

        business_rules_text += (
            f"\nTABLE: {table_name}\n"
        )

        business_rules_text += (
            "Business Key: "
            + ", ".join(
                table_rules["business_key"]
            )
            + "\n"
        )

        business_rules_text += (
            "Allowed NULL Columns: "
            + (
                ", ".join(
                    table_rules["allowed_nulls"]
                )
                if table_rules["allowed_nulls"]
                else "None"
            )
            + "\n"
        )

        business_rules_text += "Business Rules:\n"

        for rule in table_rules["rules"]:

            business_rules_text += (
                f"- {rule}\n"
            )

    return business_rules_text


# ============================================================
# 13. AI DATA QUALITY ANALYSIS FUNCTION
# ============================================================

def analyze_with_ai(quality_results):

    print("\n")

    print("=" * 70)
    print("AI DATA QUALITY ANALYSIS")
    print("=" * 70)


    # ========================================================
    # GET API KEY
    # ========================================================

    api_key = os.getenv(
        "OPENAI_API_KEY"
    )


    if not api_key:

        print(
            "\nOpenAI API key was not found."
        )

        return None


    # ========================================================
    # CREATE OPENAI CLIENT
    # ========================================================

    client = OpenAI(
        api_key=api_key
    )


    # ========================================================
    # PREPARE DQ RESULTS
    # ========================================================

    dq_text = ""


    for result in quality_results:

        dq_text += f"""
Table: {result['table']}
Rows: {result['rows']}
Unexpected NULLs: {result['unexpected_nulls']}
Allowed NULLs: {result['allowed_nulls']}
Duplicate Business Keys: {result['duplicate_keys']}
Status: {result['status']}

"""


    # ========================================================
    # PREPARE BUSINESS RULES
    # ========================================================

    business_rules_text = (
        prepare_business_rules()
    )


    # ========================================================
    # AI PROMPT
    # ========================================================

    prompt = f"""
You are an expert Data Quality Analyst working on a
SQL Server data warehouse.

Your job is to analyze Silver-layer data quality results
using the predefined business rules.

IMPORTANT PRINCIPLES:

1. The Python data-quality engine is the source of truth
   for the actual validation results.

2. The business rules provided below are the source of truth
   for interpreting those results.

3. Do NOT invent new business rules.

4. Do NOT override the Python validation results.

5. Allowed NULL values are NOT data-quality problems.

6. Unexpected NULL values should be treated as potential
   data-quality issues.

7. Duplicate business keys should be investigated according
   to the defined business key and table grain.

8. A PASS table should be recognized as healthy.

9. For WARNING or FAILED tables, determine severity based
   on the available evidence and the proportion of affected
   records.

10. Do not claim a definite root cause when the available
    information only supports a possible cause.

11. Clearly distinguish between:
    - observed issue
    - likely cause
    - recommendation

============================================================
BUSINESS RULES
============================================================

{business_rules_text}

============================================================
DATA QUALITY RESULTS
============================================================

{dq_text}

============================================================
REQUIRED AI RESPONSE
============================================================

For every WARNING or FAILED table, provide:

Table:
Severity: LOW / MEDIUM / HIGH

Observed Issue:
Explain exactly what the Python DQ engine detected.

Business Rule Interpretation:
Explain how the relevant business rule affects
the interpretation.

Likely Cause:
Give a probable cause only when supported by the data.

Recommendation:
Give a practical recommendation for a data engineer.

Then provide:

Overall Pipeline Assessment:
Healthy Tables:
Warning Tables:
Failed Tables:

Keep the response concise, technical, and business-aware.
"""


    # ========================================================
    # SEND REQUEST TO OPENAI
    # ========================================================

    try:

        response = client.responses.create(

            model="gpt-5-mini",

            input=prompt
        )

        return response.output_text


    except Exception as e:

        print(
            "\nAI analysis could not be completed."
        )

        print(
            f"Reason: {e}"
        )

        return None


# ============================================================
# 14. RUN AI ANALYSIS
# ============================================================

ai_report = analyze_with_ai(
    quality_results
)


# ============================================================
# 15. DISPLAY AI REPORT
# ============================================================

if ai_report:

    print("\n")

    print("=" * 70)
    print("AI DATA QUALITY REPORT")
    print("=" * 70)

    print("\n")

    print(ai_report)

else:

    print("\n")

    print(
        "AI report was not generated."
    )

    print(
        "The Python data-quality engine completed successfully."
    )


# ============================================================
# 16. CLOSE SQL SERVER CONNECTION
# ============================================================

cursor.close()

conn.close()


print("\n")

print(
    "SQL Server connection closed."
)

print(
    "\nAI Data Quality Agent execution completed."
)
