
from pathlib import Path


DEPARTMENTS = {

    "stickering": {
        "name": "Stickering",

        "output_root": "D:\Barcode_testing\Stickering",

        # Stage 1: Upload CSV
        "upload_url": (
            "http://localhost/ERP/BarcodeRead/custom/"
            "stickeringbarcode.php"
        ),

        # Stage 2: Submit uploaded data
        "submit_url": (
            "http://localhost/ERP/BarcodeRead/custom/"
            "stickeringbarcodeprocess.php"
        ),

        # Stage 3: Final ERP processing
        "process_url": (
            "http://localhost/ERP/BarcodeRead/custom/"
            "processsticker.php"
        ),

        "enabled": True,
    },


    "conv_start": {
        "name": "Conv Start",

        "output_root": Path(
            r"D:\Barcode_testing\Conv Start"
        ),

        # Stage 1: Upload CSV
        "upload_url": None,

        # Stage 2: Submit uploaded data
        "submit_url": None,

        # Stage 3: Final ERP processing
        "process_url": None,

        "enabled": True,
    },


    "conv_end": {
        "name": "Conv End",

        "output_root": "D:\Barcode_testing\Conv End",

        # Stage 1: Upload CSV
        "upload_url": None,

        # Stage 2: Submit uploaded data
        "submit_url": None,

        # Stage 3: Final ERP processing
        "process_url": None,

        "enabled": True,
    },


    "final_packing": {
        "name": "Final Packing",

        "output_root": "D:\Barcode_testing\Fp",

        # Stage 1: Upload CSV
        "upload_url": None,

        # Stage 2: Submit uploaded data
        "submit_url": None,

        # Stage 3: Final ERP processing
        "process_url": None,

        "enabled": True,
    },


    "store_fgs": {
        "name": "Store FGS",

        "output_root": "D:\Barcode_testing\FGS",

        # Stage 1: Upload CSV
        "upload_url": None,

        # Stage 2: Submit uploaded data
        "submit_url": None,

        # Stage 3: Final ERP processing
        "process_url": None,

        "enabled": True,
    },

}


def get_department(department_id):
    """
    Return configuration for one department.
    """

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
    """
    Return department names for the dashboard dropdown.
    """

    return {
        department_id: department["name"]
        for department_id, department in DEPARTMENTS.items()
        if department["enabled"]
    }


def validate_department_config(department_id):
    """
    Check whether all required settings are configured.
    """

    department = get_department(department_id)

    required_settings = [
        "output_root",
        "upload_url",
        "submit_url",
        "process_url",
    ]

    missing_settings = [
        setting
        for setting in required_settings
        if department[setting] is None
    ]

    if missing_settings:
        raise ValueError(
            f"{department['name']} configuration is incomplete: "
            + ", ".join(missing_settings)
        )

    return True
