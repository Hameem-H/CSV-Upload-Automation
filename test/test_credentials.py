from dotenv import load_dotenv
import os

load_dotenv()

username = os.getenv("ERP_USERNAME")
password = os.getenv("ERP_PASSWORD")

print("Username configured:", bool(username))
print("Password configured:", bool(password))