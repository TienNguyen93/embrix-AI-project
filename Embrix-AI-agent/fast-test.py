import psycopg2
conn = psycopg2.connect(
    host="10.22.16.238",
    port=5432,
    dbname="coredb",
    user="ebrx-ro-dev",
    password="AEaKIn4A5u3nDv3I47EVIOKD7q4mG71MPt28mfri",
    sslmode="require"
)
print("Connected!")