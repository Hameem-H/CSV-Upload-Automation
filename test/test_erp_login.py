
from dotenv import load_dotenv
import os
import requests

load_dotenv()

BASE_URL = "http://localhost/ERP/BarcodeRead/"
LOGIN_URL = BASE_URL + "login.php"
MENU_URL = BASE_URL + "menu.php"

username = os.getenv("ERP_USERNAME")
password = os.getenv("ERP_PASSWORD")

if not username or not password:
    raise ValueError("ERP credentials missing from .env")

with requests.Session() as session:

    print("Opening login page...")

    login_page = session.get(LOGIN_URL, timeout=30)
    print("Login page:", login_page.status_code)

    print("\nSubmitting credentials...")

    response = session.post(
        LOGIN_URL,
        data={
            "username": username,
            "pass": password,
            "login": "Submit"
        },
        timeout=30,
        allow_redirects=True
    )

    print("Login response:", response.status_code)
    print("Final URL:", response.url)
    print("Session cookies:", session.cookies.get_dict())

    print("\nTesting menu access...")

    menu_response = session.get(
        MENU_URL,
        timeout=30,
        allow_redirects=True
    )

    print("Menu response:", menu_response.status_code)
    print("Menu final URL:", menu_response.url)

    if menu_response.url.lower().endswith("/login.php"):
        print("\nFAILED: ERP redirected Python to login.")
    elif "name=\"username\"" in menu_response.text.lower():
        print("\nFAILED: Login form still appears.")
    else:
        print("\nMenu access appears successful.")
        print("Please inspect the response before proceeding.")
