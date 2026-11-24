"""
Four-page workflow for Conv Start, Conv End, Final Packing and Store FGS.

Page 1: CSV upload.
Page 2: Submit uploaded CSV.
Page 3: Intermediate PHP processing page; its PHP code runs and displays
        a button that submits to Page 4.
Page 4: Final processing endpoint.

This module is intentionally not wired into the main client until the
remaining department URLs and Page 3 URL have been confirmed.
"""


def process_standard_department(*args, **kwargs):
    raise NotImplementedError(
        "The four-page workflow is not connected yet. "
        "Confirm the Page 3 URL and the department-specific URLs first."
    )
