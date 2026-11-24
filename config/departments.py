
from pathlib import Path


ERP_BASE_URL = "http://localhost/ERP/BarcodeRead/custom"


DEPARTMENTS = {

    "stickering": {
        "name": "Stickering",

        "output_root": Path(r"D:\Barcode_testing\Stickering"),

        "upload_url": (
            f"{ERP_BASE_URL}/stickeringbarcode.php"
        ),

        "submit_url": (
            f"{ERP_BASE_URL}/stickeringbarcodeprocess.php"
        ),

        # Stickering has no separate Page 3.
        "intermediate_url": None,

        # Existing final processing page.
        "process_url": (
            f"{ERP_BASE_URL}/ProcessSticker.php"
        ),

        "workflow": "three_page",
        "enabled": True,
    },


    "conv_start": {
        "name": "Conv Start",

        "output_root": Path(r"D:\Barcode_testing\Conv Start"),

        "upload_url": None,
        "submit_url": None,
        "intermediate_url": None,
        "process_url": None,

        "workflow": "four_page",
        "enabled": True,
    },


    "conv_end": {
        "name": "Conv End",

        "output_root": Path(r"D:\Barcode_testing\Conv End"),

        "upload_url": None,
        "submit_url": None,
        "intermediate_url": None,
        "process_url": None,

        "workflow": "four_page",
        "enabled": True,
    },


    "final_packing": {
        "name": "Final Packing",

        "output_root": Path(r"D:\Barcode_testing\Fp"),

        # Page 1: CSV upload
        "upload_url": (
            f"{ERP_BASE_URL}/FPbarcode.php"
        ),

        # Page 2: Submit CSV
        "submit_url": (
            f"{ERP_BASE_URL}/FPbarcodeprocess.php"
        ),

        # Page 3: Intermediate processing page
        "intermediate_url": (
            f"{ERP_BASE_URL}/ProcessFP.php"
        ),

        # Page 4: Final processing page
        "process_url": (
            f"{ERP_BASE_URL}/FPL1finalpro.php"
        ),

        "workflow": "four_page",
        "enabled": True,
    },


    "store_fgs": {
        "name": "Store FGS",

        "output_root": Path(r"D:\Barcode_testing\FGS"),

        "upload_url": None,
        "submit_url": None,
        "intermediate_url": None,
        "process_url": None,

        "workflow": "four_page",
        "enabled": True,
    },

}


def get_department(department_id):

    if department_id not in DEPARTMENTS:
        raise ValueError(
            f"Unknown department: {department_id}"
        )

    department = DEPARTMENTS[department_id]

    if not department["enabled"]:
        raise ValueError(
            f"{department['name']} is currently disabled."
        )

    return department


def get_department_names():

    return {
        department_id: department["name"]
        for department_id, department in DEPARTMENTS.items()
        if department["enabled"]
    }


def validate_department_config(department_id):

    department = get_department(department_id)

    required_settings = [
        "output_root",
        "upload_url",
        "submit_url",
        "process_url",
    ]

    if department["workflow"] == "four_page":
        required_settings.append("intermediate_url")

    missing_settings = [
        setting
        for setting in required_settings
        if department.get(setting) is None
    ]

    if missing_settings:
        raise ValueError(
            f"{department['name']} configuration is incomplete: "
            + ", ".join(missing_settings)
        )

    return True
