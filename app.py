
from datetime import datetime
from pathlib import Path

import streamlit as st

from config.departments import (
    get_department,
    get_department_names,
)

from core.parser import parse_scanner_txt
from core.duplicate_processor import build_outputs
from core.report_generator import generate_processing_summary
from storage.file_manager import save_outputs

from automation.erp_client import (
    upload_and_process,
    ERPStageError,
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
# PAGE HEADER
# --------------------------------------------------

st.title("Barcode Automation Dashboard")

st.caption(
    "Scanner TXT processing, duplicate removal and ERP CSV preparation"
)

st.divider()


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "erp_result" not in st.session_state:
    st.session_state.erp_result = None


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

    # ----------------------------------------------
    # STORAGE DATE OVERRIDE
    # ----------------------------------------------

    selected_storage_date = st.date_input(
        "Storage Date",
        value=datetime.now().date(),
        help=(
            "By default, today's date is selected. "
            "Change this date when processing historical scanner data. "
            "This date controls the output folder and processing summary."
        )
    )

    st.caption(
        "The selected date affects file storage only. "
        "Barcode record dates and ERP upload behavior will not change."
    )

    uploaded_file = st.file_uploader(
        "Upload scanner TXT file",
        type=["txt"],
        help="Select the original scanner TXT file."
    )

    submitted = st.form_submit_button(
        "Start Processing",
        type="primary",
        width="stretch"
    )


# --------------------------------------------------
# PROCESSING PIPELINE
# --------------------------------------------------

if submitted:

    # Clear previous results before processing a new file.
    st.session_state.last_result = None
    st.session_state.erp_result = None

    if uploaded_file is None:

        st.error("Please upload a TXT file first.")

    else:

        try:

            department = get_department(selected_department)

            original_file_bytes = uploaded_file.getvalue()
            original_filename = uploaded_file.name

            # Use selected date instead of always using today's date.
            # Keep the current time for the processing timestamp.
            processing_date = datetime.combine(
                selected_storage_date,
                datetime.now().time()
            )

            # --------------------------------------
            # STEP 1: PARSING
            # --------------------------------------

            with st.status(
                "Step 1/5: Reading and parsing TXT file...",
                expanded=True
            ) as status:

                valid_df, invalid_df = parse_scanner_txt(
                    original_file_bytes
                )

                total_rows = len(valid_df)
                invalid_count = len(invalid_df)

                st.write(
                    f"Valid records: {total_rows:,}"
                )

                st.write(
                    f"Invalid records: {invalid_count:,}"
                )

                status.update(
                    label="Step 1/5: TXT parsing completed",
                    state="complete"
                )

            # --------------------------------------
            # STEP 2: DUPLICATE PROCESSING
            # --------------------------------------

            with st.status(
                "Step 2/5: Checking duplicate barcodes...",
                expanded=True
            ) as status:

                (
                    unique_df,
                    duplicate_rows_df,
                    duplicate_summary_df,
                    total_rows,
                    unique_count,
                    duplicate_count
                ) = build_outputs(valid_df)

                st.write(
                    f"Unique barcodes: {unique_count:,}"
                )

                st.write(
                    f"Duplicate records: {duplicate_count:,}"
                )

                status.update(
                    label="Step 2/5: Duplicate processing completed",
                    state="complete"
                )

            # --------------------------------------
            # STEP 3: SUMMARY GENERATION
            # --------------------------------------

            with st.status(
                "Step 3/5: Generating processing summary...",
                expanded=True
            ) as status:

                summary_text = generate_processing_summary(
                    department_name=department["name"],
                    original_filename=original_filename,
                    total_rows=total_rows,
                    unique_count=unique_count,
                    duplicate_count=duplicate_count,
                    invalid_count=invalid_count,
                    processing_date=processing_date
                )

                status.update(
                    label="Step 3/5: Summary generated",
                    state="complete"
                )

            # --------------------------------------
            # STEP 4: FILE SAVING
            # --------------------------------------

            with st.status(
                "Step 4/5: Saving output files...",
                expanded=True
            ) as status:

                saved_files = save_outputs(
                    department_id=selected_department,
                    original_file_bytes=original_file_bytes,
                    original_filename=original_filename,
                    unique_df=unique_df,
                    duplicate_rows_df=duplicate_rows_df,
                    duplicate_summary_df=duplicate_summary_df,
                    invalid_df=invalid_df,
                    total_rows=total_rows,
                    unique_count=unique_count,
                    duplicate_count=duplicate_count,
                    summary_text=summary_text,
                    processing_date=processing_date
                )

                status.update(
                    label="Step 4/5: Files saved successfully",
                    state="complete"
                )

            # --------------------------------------
            # STEP 5: ERP PREPARATION
            # --------------------------------------

            with st.status(
                "Step 5/5: Preparing ERP upload data...",
                expanded=True
            ) as status:

                erp_csv_path = Path(
                    saved_files["erp_csv_path"]
                )

                st.write(
                    f"ERP CSV prepared: {erp_csv_path.name}"
                )

                st.write(
                    "ERP upload has not been started."
                )

                status.update(
                    label="Step 5/5: ERP CSV preparation completed",
                    state="complete"
                )

            # --------------------------------------
            # SAVE RESULT FOR DISPLAY
            # --------------------------------------

            st.session_state.last_result = {
                "department": department["name"],

                # Required for ERP configuration lookup.
                "department_id": selected_department,

                "filename": original_filename,
                "storage_date": selected_storage_date,
                "saved_files": saved_files,

                "valid_df": valid_df,
                "invalid_df": invalid_df,
                "unique_df": unique_df,
                "duplicate_rows_df": duplicate_rows_df,
                "duplicate_summary_df": duplicate_summary_df,

                "summary_text": summary_text,

                "total_rows": total_rows,
                "unique_count": unique_count,
                "duplicate_count": duplicate_count,
                "invalid_count": invalid_count,
            }

            st.success(
                "Barcode processing completed successfully!"
            )

        except FileExistsError as error:

            st.error(
                "Files already exist for this department and date. "
                "No existing files were overwritten."
            )

            st.code(str(error))

        except Exception as error:

            st.error("Processing failed.")
            st.exception(error)


# --------------------------------------------------
# GET LATEST PROCESSING RESULT
# --------------------------------------------------

result = st.session_state.last_result


# --------------------------------------------------
# ERP UPLOAD SECTION
# This appears after the Start Processing pipeline.
# The upload button is never blocked by browser status.
# --------------------------------------------------

st.divider()

st.subheader("2. ERP Upload")

if not result:

    st.info(
        "Process a TXT file first to prepare the ERP CSV."
    )

else:

    last_result = result

    erp_csv_path = Path(
        last_result["saved_files"]["erp_csv_path"]
    )

    department_id = last_result["department_id"]

    department = get_department(department_id)

    st.write(
        f"**Department:** {department['name']}"
    )

    st.write(
        f"**ERP CSV:** `{erp_csv_path.name}`"
    )

    if not erp_csv_path.is_file():

        st.error(
            "The ERP CSV file could not be found."
        )

    else:

        st.warning(
            "ERP processing may take several minutes. "
            "Do not retry unless you have checked ERP records."
        )

        required_urls = [
            "upload_url",
            "submit_url",
            "process_url"
        ]

        missing_urls = [
            key
            for key in required_urls
            if not department.get(key)
        ]

        if missing_urls:

            st.warning(
                f"ERP automation is not configured for "
                f"{department['name']} yet."
            )

        else:

            # --------------------------------------
            # BROWSER STATUS
            # --------------------------------------

            if is_erp_browser_open():

                st.info(
                    "An ERP browser is already open. "
                    "The next upload will use that browser "
                    "and open a new tab."
                )

            else:

                st.caption(
                    "An ERP browser will open when you start uploading."
                )

            # --------------------------------------
            # UPLOAD BUTTON
            # --------------------------------------
            #
            # IMPORTANT:
            # This button is always available.
            # Browser status does not disable or hide it.
            # --------------------------------------

            if st.button(
                "Upload to ERP",
                type="primary",
                width="stretch",
                key="upload_to_erp"
            ):

                progress_messages = []

                with st.status(
                    "ERP automation running...",
                    expanded=True
                ) as erp_status:

                    progress_area = st.empty()

                    def update_erp_progress(
                        stage,
                        message,
                        state="running",
                        details=None
                    ):

                        progress_messages.append(
                            f"**{stage.replace('_', ' ').title()}:** {message}"
                        )

                        progress_area.markdown(
                            "\n\n".join(progress_messages)
                        )

                    try:

                        erp_result = upload_and_process(
                            department=department,
                            csv_path=erp_csv_path,
                            progress_callback=update_erp_progress
                        )

                        st.session_state.erp_result = erp_result

                        erp_status.update(
                            label="ERP automation completed",
                            state="complete",
                            expanded=True
                        )

                        st.success(
                            erp_result["message"]
                        )

                    except ERPStageError as error:

                        st.session_state.erp_result = (
                            error.result if error.result else None
                        )

                        erp_status.update(
                            label="ERP automation failed",
                            state="error",
                            expanded=True
                        )

                        st.error(str(error))

                        st.warning(
                            "Do not upload again until ERP records "
                            "have been checked."
                        )

                    except Exception as error:

                        st.session_state.erp_result = None

                        erp_status.update(
                            label="Unexpected ERP error",
                            state="error",
                            expanded=True
                        )

                        st.exception(error)

            # --------------------------------------
            # CLOSE BROWSER BUTTON
            # --------------------------------------
            #
            # Separate from Upload to ERP.
            # Closing is optional and never required
            # before starting another upload.
            # --------------------------------------

            if is_erp_browser_open():

                if st.button(
                    "Close ERP Browser",
                    key="close_erp_browser"
                ):

                    try:

                        close_erp_browser()

                        st.success(
                            "ERP browser closed."
                        )

                        st.rerun()

                    except Exception as error:

                        st.error(
                            f"Could not close ERP browser: {error}"
                        )


# --------------------------------------------------
# RESULTS SECTION
# --------------------------------------------------

if result:

    st.divider()

    st.subheader("3. Processing Results")

    st.write(
        f"**Department:** {result['department']}"
    )

    st.write(
        f"**Original file:** {result['filename']}"
    )

    st.write(
        f"**Storage date:** "
        f"{result['storage_date'].strftime('%d-%m-%Y')}"
    )

    # ----------------------------------------------
    # SUMMARY METRICS
    # ----------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Valid Records",
        f"{result['total_rows']:,}"
    )

    col2.metric(
        "Unique Barcodes",
        f"{result['unique_count']:,}"
    )

    col3.metric(
        "Duplicate Records",
        f"{result['duplicate_count']:,}"
    )

    col4.metric(
        "Invalid Records",
        f"{result['invalid_count']:,}"
    )

    # ----------------------------------------------
    # DATA PREVIEWS
    # ----------------------------------------------

    st.subheader("4. Data Inspection")

    tab1, tab2, tab3, tab4 = st.tabs([
        "ERP CSV Preview",
        "Duplicate Records",
        "Invalid Lines",
        "Duplicate Summary"
    ])

    with tab1:

        st.caption(
            "These are the unique records prepared for ERP upload. "
            "The actual saved CSV has no header or index."
        )

        st.dataframe(
            result["unique_df"],
            width="stretch",
            hide_index=True
        )

    with tab2:

        st.write(
            f"Duplicate rows found: "
            f"{result['duplicate_count']:,}"
        )

        st.dataframe(
            result["duplicate_rows_df"],
            width="stretch",
            hide_index=True
        )

    with tab3:

        st.write(
            f"Invalid lines found: "
            f"{result['invalid_count']:,}"
        )

        st.dataframe(
            result["invalid_df"],
            width="stretch",
            hide_index=True
        )

    with tab4:

        st.dataframe(
            result["duplicate_summary_df"],
            width="stretch",
            hide_index=True
        )

    # ----------------------------------------------
    # SAVED FILE LOCATIONS
    # ----------------------------------------------

    st.divider()

    st.subheader("5. Saved Files")

    saved_files = result["saved_files"]

    st.write(
        f"**Output folder:** `{saved_files['daily_folder']}`"
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

        if key not in saved_files:
            continue

        file_path = Path(saved_files[key])

        if file_path.exists():

            st.write(
                f"✅ **{label}:** `{file_path}`"
            )

    # ----------------------------------------------
    # PROCESSING SUMMARY
    # ----------------------------------------------

    with st.expander("View Processing Summary"):

        st.text(result["summary_text"])


# --------------------------------------------------
# ERP RESULT DISPLAY
# --------------------------------------------------

erp_result = st.session_state.get("erp_result")

if isinstance(erp_result, dict) and erp_result:

    st.divider()

    st.subheader("6. ERP Automation Result")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Upload HTTP Status",
        erp_result.get("upload_http_status") or "N/A"
    )

    col2.metric(
        "Processing HTTP Status",
        erp_result.get("http_status") or "N/A"
    )

    processing_time = erp_result.get(
        "processing_time_seconds"
    )

    col3.metric(
        "Processing Time",
        (
            f"{processing_time} sec"
            if processing_time is not None
            else "N/A"
        )
    )

    col4.metric(
        "Completion Verified",
        "Yes" if erp_result.get("completion_verified") else "No"
    )

    st.write(
        f"**Department:** {erp_result.get('department', 'N/A')}"
    )

    st.write(
        f"**Message:** {erp_result.get('message', 'N/A')}"
    )

    st.write("**Workflow stages:**")

    for stage, details in erp_result.get("stages", {}).items():

        if details.get("success"):

            st.write(
                f"✅ **{stage.replace('_', ' ').title()}:** Completed"
            )

        else:

            st.write(
                f"❌ **{stage.replace('_', ' ').title()}:** Not completed"
            )

    if is_erp_browser_open():

        st.info(
            "Chromium is still open. You can inspect the ERP page "
            "or start another upload from Section 2."
        )

elif erp_result is None:

    st.info(
        "No ERP automation result is available yet. "
        "Prepare a CSV and start ERP upload when ready."
    )

else:

    st.warning(
        "ERP result has an unexpected format."
    )
