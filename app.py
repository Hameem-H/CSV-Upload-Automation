
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

    uploaded_file = st.file_uploader(
        "Upload scanner TXT file",
        type=["txt"],
        help="Select the original scanner TXT file."
    )

    submitted = st.form_submit_button(
        "Start Processing",
        type="primary",
        use_container_width=True
    )


# --------------------------------------------------
# PROCESSING PIPELINE
# --------------------------------------------------

if submitted:

    st.session_state.last_result = None

    if uploaded_file is None:
        st.error("Please upload a TXT file first.")

    else:

        try:
            department = get_department(selected_department)

            original_file_bytes = uploaded_file.getvalue()
            original_filename = uploaded_file.name

            processing_date = datetime.now()

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

                erp_csv_path = saved_files["erp_csv_path"]

                status.write(
                    f"ERP CSV prepared: {erp_csv_path.name}"
                )

                status.write(
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
                "filename": original_filename,
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

            st.success("Barcode processing completed successfully!")

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
# RESULTS SECTION
# --------------------------------------------------

result = st.session_state.last_result

if result:

    st.divider()

    st.subheader("2. Processing Results")

    st.write(
        f"**Department:** {result['department']}"
    )

    st.write(
        f"**Original file:** {result['filename']}"
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

    st.subheader("3. Data Inspection")

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
            use_container_width=True,
            hide_index=True
        )

    with tab2:
        st.write(
            f"Duplicate rows found: "
            f"{result['duplicate_count']:,}"
        )

        st.dataframe(
            result["duplicate_rows_df"],
            use_container_width=True,
            hide_index=True
        )

    with tab3:
        st.write(
            f"Invalid lines found: "
            f"{result['invalid_count']:,}"
        )

        st.dataframe(
            result["invalid_df"],
            use_container_width=True,
            hide_index=True
        )

    with tab4:
        st.dataframe(
            result["duplicate_summary_df"],
            use_container_width=True,
            hide_index=True
        )

    # ----------------------------------------------
    # SAVED FILE LOCATIONS
    # ----------------------------------------------

    st.divider()

    st.subheader("4. Saved Files")

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

    # ----------------------------------------------
    # ERP STATUS
    # ----------------------------------------------

    st.divider()

    st.subheader("5. ERP Upload Status")

    st.info(
        "The ERP CSV is ready, but no ERP request has been sent. "
        "ERP automation will be implemented and tested separately."
    )
