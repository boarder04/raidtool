import sqlite3

def print_table_data(cursor, table_name):
    print(f"Contents of table '{table_name}':")
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    print()  # Add an empty line for better readability between tables

def output_database():
    # Connect to the SQLite database
    conn = sqlite3.connect('raidbot.db')
    cursor = conn.cursor()

    # List of your table names
    table_names = ['raids', 'items', 'rolls']

    # Loop through each table and print its contents
    for table_name in table_names:
        print_table_data(cursor, table_name)

    # Close the connection
    conn.close()

# Run the function to output the database contents
output_database()

