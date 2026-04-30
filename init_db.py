"""
init_db.py – Run this ONCE to set up the users database and create the first admin account.

Usage:
    cd flask_bot
    python init_db.py
    python init_db.py --add-user john secret123
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from auth import init_db, create_user

def main():
    # Always ensure the table exists
    init_db()
    print("[OK] Database initialized.")

    args = sys.argv[1:]

    if "--add-user" in args:
        idx = args.index("--add-user")
        try:
            username = args[idx + 1]
            password = args[idx + 2]
        except IndexError:
            print("Usage: python init_db.py --add-user <username> <password>")
            sys.exit(1)

        if create_user(username, password):
            print(f"[OK] User '{username}' created successfully.")
        else:
            print(f"[!] User '{username}' already exists.")
    else:
        # Create a default admin user on first run
        if create_user("admin", "admin"):
            print("[OK] Default user created  ->  username: admin  |  password: admin")
            print("[!!] Please change the password after first login!")
        else:
            print("[i] User 'admin' already exists. Use --add-user to add more users.")

if __name__ == "__main__":
    main()
