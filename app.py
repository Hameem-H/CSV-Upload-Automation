
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from config.departments import get_department_names

from jobs.job_manager import (
    submit_job,
    get_jobs,
    get_running_jobs,
    initialize_job_manager,
    has_active_jobs,
)

from automation.erp_client import (
    upload_and_process,
    ERPStageError,
)

from automation.browser_manager import (
    close_erp_browser,
    is_erp_browser_open,
)


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="Barcode Automation",
    page_icon="📦",
    layout="wide"
)


# --------------------------------------------------
# INITIALIZATION
# --------------------------------------------------

initialize_job_manager()


if "uploader_generation" not in st.session_state:
    st.session_state.uploader_generation = 0

if "last_submitted_job" not in st.session_state:
    st.session_state.last_submitted_job = None


# --------------------------------------------------
# PAGE HEADER
# --------------------------------------------------

st.title("Barcode Automation Dashboard")

st.caption(
    "Scanner TXT processing, duplicate removal and automatic ERP upload"
)

st.divider()


# --------------------------------------------------
# DEPARTMENT CONFIGURATION
# --------------------------------------------------

department_options = get_department_names()

if not department_options:

    st.error("No departments are currently enabled.")
    st.stop()


# --------------------------------------------------
# INPUT SECTION
# --------------------------------------------------

st.subheader("1. Upload Scanner File")

with st.form("barcode_processing_form"):

    selected_department = st.selectbox(
        "Select Department",
        options=list(department_options.keys()),
        format_func=lambda department_id: department_options[
            department_id
        ]
    )

    selected_storage_date = st.date_input(
        "Storage Date",
        value=datetime.now().date(),
        help=(
            "Change this date when processing historical scanner data. "
            "It controls the output folder and processing summary."
        )
    )

    st.caption(
        "The selected date affects file storage only. "
        "Barcode record dates and ERP upload behavior will not change."
    )

    uploaded_file = st.file_uploader(
        "Upload scanner TXT file",
        type=["txt"],
        key=f"scanner_txt_{st.session_state.uploader_generation}",
        help="Select one original scanner TXT file."
    )

    submitted = st.form_submit_button(
        "Start Processing",
        type="primary",
        width="stretch"
    )


# --------------------------------------------------
# SUBMIT NEW JOB
# --------------------------------------------------

if submitted:

    if uploaded_file is None:

        st.error("Please upload a TXT file first.")

    else:

        try:

            original_file_bytes = uploaded_file.getvalue()
            original_filename = uploaded_file.name

            if not original_file_bytes:

                st.error("The uploaded TXT file is empty.")

            else:

                new_job = submit_job(
                    department_id=selected_department,
                    original_filename=original_filename,
                    original_file_bytes=original_file_bytes,
                    storage_date=selected_storage_date
                )

                st.session_state.last_submitted_job = (
                    new_job["job_id"]
                )

                # Change the uploader key so the next run
                # displays an empty file uploader.
                st.session_state.uploader_generation += 1

                st.rerun()

        except Exception as error:

            st.error("Could not submit the processing job.")
            st.exception(error)


# --------------------------------------------------
# SUBMISSION CONFIRMATION
# --------------------------------------------------

if st.session_state.last_submitted_job:

    st.success(
        f"Job submitted successfully: "
        f"{st.session_state.last_submitted_job}"
    )

    st.caption(
        "You can now select another TXT file while this job continues "
        "in the background."
    )


# --------------------------------------------------
# JOB STATUS DASHBOARD
# --------------------------------------------------

st.divider()

st.subheader("2. Job Dashboard")


@st.fragment(run_every="2s")
def render_job_dashboard():

    jobs = get_jobs()
    active_jobs = get_running_jobs()

    # ----------------------------------------------
    # JOB COUNTERS
    # ----------------------------------------------

    total_jobs = len(jobs)

    queued_jobs = sum(
        1 for job in jobs
        if job["status"] == "queued"
    )

    preparing_jobs = sum(
        1 for job in jobs
        if job["status"] == "preparing"
    )

    running_jobs = sum(
        1 for job in jobs
        if job["status"] == "running"
    )

    completed_jobs = sum(
        1 for job in jobs
        if job["status"] == "completed"
    )

    failed_jobs = sum(
        1 for job in jobs
        if job["status"] in ("failed", "interrupted")
    )

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Total Jobs", total_jobs)

    col2.metric(
        "Preparing / Queued",
        preparing_jobs + queued_jobs
    )

    col3.metric("ERP Running", running_jobs)

    col4.metric("Completed", completed_jobs)

    col5.metric("Failed", failed_jobs)

    st.divider()

    # ----------------------------------------------
    # ACTIVE JOBS
    # ----------------------------------------------

    st.markdown("### Active Jobs")

    if not active_jobs:

        st.info("There are currently no active jobs.")

    else:

        for job in active_jobs:

            with st.container(border=True):

                st.markdown(
                    f"**{job['job_id']} — {job['department']}**"
                )

                st.caption(
                    f"File: {job['original_filename']}"
                )

                st.write(
                    f"**Status:** {job['status'].replace('_', ' ').title()}"
                )

                st.write(
                    f"**Stage:** {job['stage']}"
                )

                st.progress(
                    job.get("progress", 0),
                    text=job.get("message", "")
                )

                if job["status"] == "queued":

                    st.caption(
                        "Preparation is complete. Waiting for the ERP worker."
                    )

    # ----------------------------------------------
    # JOB HISTORY
    # ----------------------------------------------

    st.divider()

    st.markdown("### All Jobs")

    if not jobs:

        st.info(
            "No jobs have been submitted yet. "
            "Upload a scanner TXT file to get started."
        )

    else:

        for job in jobs:

            status = job["status"]

            if status == "completed":
                status_icon = "✅"

            elif status == "failed":
                status_icon = "❌"

            elif status == "interrupted":
                status_icon = "⚠️"

            elif status == "running":
                status_icon = "🔄"

            elif status == "queued":
                status_icon = "⏳"

            else:
                status_icon = "⚙️"

            expander_title = (
                f"{status_icon} {job['job_id']} | "
                f"{job['department']} | "
                f"{job['original_filename']}"
            )

            with st.expander(expander_title):

                # ----------------------------------
                # JOB INFORMATION
                # ----------------------------------

                col1, col2 = st.columns(2)

                with col1:

                    st.write(
                        f"**Job ID:** {job['job_id']}"
                    )

                    st.write(
                        f"**Department:** {job['department']}"
                    )

                    st.write(
                        f"**Original file:** {job['original_filename']}"
                    )

                    st.write(
                        f"**Storage date:** {job['storage_date']}"
                    )

                with col2:

                    st.write(
                        f"**Status:** {status.replace('_', ' ').title()}"
                    )

                    st.write(
                        f"**Created:** {job['created_at']}"
                    )

                    st.write(
                        f"**Started:** {job.get('started_at') or 'Not started'}"
                    )

                    st.write(
                        f"**Completed:** {job.get('completed_at') or 'Not completed'}"
                    )

                st.progress(
                    job.get("progress", 0),
                    text=job.get("message", "")
                )

                # ----------------------------------
                # PROCESSING METRICS
                # ----------------------------------

                metrics = job.get("metrics", {})

                if metrics:

                    st.markdown("#### Processing Metrics")

                    col1, col2, col3, col4 = st.columns(4)

                    col1.metric(
                        "Valid Records",
                        f"{metrics.get('total_rows', 0):,}"
                    )

                    col2.metric(
                        "Unique Barcodes",
                        f"{metrics.get('unique_count', 0):,}"
                    )

                    col3.metric(
                        "Duplicates",
                        f"{metrics.get('duplicate_count', 0):,}"
                    )

                    col4.metric(
                        "Invalid Records",
                        f"{metrics.get('invalid_count', 0):,}"
                    )

                # ----------------------------------
                # SAVED FILES
                # ----------------------------------

                saved_files = job.get("saved_files", {})

                if saved_files:

                    st.markdown("#### Saved Files")

                    st.write(
                        f"**Output folder:** "
                        f"`{saved_files.get('daily_folder', 'N/A')}`"
                    )

                    file_labels = {
                        "original_txt_path": "Original TXT",
                        "erp_csv_path": "ERP CSV",
                        "duplicate_details_path": "Duplicate Details",
                        "duplicate_summary_path": "Duplicate Summary",
                        "invalid_lines_path": "Invalid Lines",
                        "processing_summary_path": "Processing Summary",
                    }

                    for key, label in file_labels.items():

                        file_path = saved_files.get(key)

                        if file_path and Path(file_path).is_file():

                            st.write(
                                f"**{label}:** `{file_path}`"
                            )

                # ----------------------------------
                # DATA INSPECTION
                # ----------------------------------

                if saved_files:

                    with st.expander("Inspect Job Data"):

                        # ERP CSV
                        erp_csv = saved_files.get("erp_csv_path")

                        if erp_csv and Path(erp_csv).is_file():

                            st.markdown("**ERP CSV Preview**")

                            try:

                                erp_df = pd.read_csv(
                                    erp_csv,
                                    header=None,
                                    names=[
                                        "Date",
                                        "Time",
                                        "ScannerID",
                                        "BarcodeNumber"
                                    ]
                                )

                                st.dataframe(
                                    erp_df,
                                    width="stretch",
                                    hide_index=True
                                )

                            except Exception as error:

                                st.warning(
                                    f"Could not read ERP CSV: {error}"
                                )

                        # Duplicate details
                        duplicate_file = saved_files.get(
                            "duplicate_details_path"
                        )

                        if duplicate_file and Path(duplicate_file).is_file():

                            st.markdown("**Duplicate Records**")

                            try:

                                duplicate_df = pd.read_csv(
                                    duplicate_file
                                )

                                st.dataframe(
                                    duplicate_df,
                                    width="stretch",
                                    hide_index=True
                                )

                            except Exception as error:

                                st.warning(
                                    f"Could not read duplicate report: {error}"
                                )

                        # Invalid lines
                        invalid_file = saved_files.get(
                            "invalid_lines_path"
                        )

                        if invalid_file and Path(invalid_file).is_file():

                            st.markdown("**Invalid Lines**")

                            try:

                                invalid_df = pd.read_csv(
                                    invalid_file
                                )

                                st.dataframe(
                                    invalid_df,
                                    width="stretch",
                                    hide_index=True
                                )

                            except Exception as error:

                                st.warning(
                                    f"Could not read invalid report: {error}"
                                )

                        # Duplicate summary
                        summary_file = saved_files.get(
                            "duplicate_summary_path"
                        )

                        if summary_file and Path(summary_file).is_file():

                            st.markdown("**Duplicate Summary**")

                            try:

                                duplicate_summary_df = pd.read_csv(
                                    summary_file
                                )

                                st.dataframe(
                                    duplicate_summary_df,
                                    width="stretch",
                                    hide_index=True
                                )

                            except Exception as error:

                                st.warning(
                                    f"Could not read duplicate summary: {error}"
                                )

                        # Processing summary
                        processing_summary_file = saved_files.get(
                            "processing_summary_path"
                        )

                        if (
                            processing_summary_file
                            and Path(processing_summary_file).is_file()
                        ):

                            with st.expander("Processing Summary"):

                                st.text(
                                    Path(processing_summary_file).read_text(
                                        encoding="utf-8"
                                    )
                                )

                # ----------------------------------
                # ERP RESULT
                # ----------------------------------

                erp_result = job.get("erp_result")

                if erp_result:

                    st.markdown("#### ERP Result")

                    col1, col2, col3 = st.columns(3)

                    col1.metric(
                        "Upload HTTP Status",
                        erp_result.get("upload_http_status") or "N/A"
                    )

                    col2.metric(
                        "Processing HTTP Status",
                        erp_result.get("http_status") or "N/A"
                    )

                    col3.metric(
                        "Completion Verified",
                        (
                            "Yes"
                            if erp_result.get("completion_verified")
                            else "No"
                        )
                    )

                    st.write(
                        f"**Message:** "
                        f"{erp_result.get('message', 'N/A')}"
                    )

                    st.markdown("**Workflow Stages**")

                    for stage, details in erp_result.get(
                        "stages", {}
                    ).items():

                        if details.get("success"):

                            st.write(
                                f"✅ {stage.replace('_', ' ').title()}"
                            )

                        else:

                            st.write(
                                f"❌ {stage.replace('_', ' ').title()}"
                            )

                # ----------------------------------
                # ERROR INFORMATION
                # ----------------------------------

                if job.get("error"):

                    st.error(
                        f"Job error: {job['error']}"
                    )

                    st.warning(
                        "Check ERP records before submitting this file again."
                    )

                # ----------------------------------
                # JOB HISTORY
                # ----------------------------------

                history = job.get("history", [])

                if history:

                    with st.expander("Job Activity History"):

                        for entry in history:

                            st.write(
                                f"**{entry['timestamp']}** — "
                                f"{entry['stage']} — "
                                f"{entry['message']}"
                            )

    # ----------------------------------------------
    # ERP BROWSER MANAGEMENT
    # ----------------------------------------------

    st.divider()

    st.markdown("### ERP Browser")

    browser_open = is_erp_browser_open()
    active_jobs_exist = has_active_jobs()

    if browser_open:

        st.success("ERP browser is currently open.")

        if active_jobs_exist:

            st.warning(
                "Browser closing is disabled while jobs are active."
            )

        else:

            if st.button(
                "Close ERP Browser",
                key="close_erp_browser"
            ):

                try:

                    close_erp_browser()

                    st.success("ERP browser closed successfully.")

                except Exception as error:

                    st.error(
                        f"Could not close ERP browser: {error}"
                    )

    else:

        st.info(
            "ERP browser is currently closed. "
            "It will open automatically when the next ERP job starts."
        )


render_job_dashboard()
