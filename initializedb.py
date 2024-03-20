import sqlite3

def initialize_db(db_path='raidbot.db'):
    # Connect to the SQLite database
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # Create the 'raids' table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS raids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time DATETIME,
                end_time DATETIME,
                status TEXT
            )''')
        # Create the 'items' table with 'contested' as BOOLEAN
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raid_id INTEGER,
                name TEXT,
                winner_user_id TEXT,
                winner_username TEXT,
                contested BOOLEAN DEFAULT 1,
                FOREIGN KEY (raid_id) REFERENCES raids(id)
            )''')
        # Create the 'rolls' table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rolls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                user_id INTEGER,
                roll_type TEXT,
                random_roll_value INTEGER,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )''')

# Specify the path to your database file
db_path = 'raidbot.db'

# Call the function to initialize the database
initialize_db(db_path)

print("Database initialized successfully.")

