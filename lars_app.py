import streamlit as st
import pandas as pd
import os
import io
import re
import plotly.express as px

# --- Constants ---
LAST_RUN_FILE = "last_run_data.pkl"

# --- Page Config ---
st.set_page_config(page_title="LARS File Merger", layout="wide") 

# --- Custom CSS to fit screen and reduce font sizes ---
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            padding-left: 2rem;
            padding-right: 2rem;
            max-width: 98%;
        }
        h3 {
            font-size: 1.1rem !important;
            padding-bottom: 0.2rem !important;
        }
        p {
            font-size: 0.9rem !important;
        }
    </style>
""", unsafe_allow_html=True)

st.title("📊 ATR Remediation Status & Dashboard")
st.write("Upload the three Observation files (CSV format) to format, merge, map columns, and generate the dashboard.")

# --- Session State Initialization ---
if 'cumulative_df' not in st.session_state:
    if os.path.exists(LAST_RUN_FILE):
        try:
            st.session_state['cumulative_df'] = pd.read_pickle(LAST_RUN_FILE)
        except Exception:
            st.session_state['cumulative_df'] = None
    else:
        st.session_state['cumulative_df'] = None

# --- File Uploaders ---
col1, col2, col3 = st.columns(3)

with col1:
    file1 = st.file_uploader("1. Completed-Observation", type=['csv'])
with col2:
    file2 = st.file_uploader("2. Open-Observation", type=['csv'])
with col3:
    file3 = st.file_uploader("3. PendingApprovalObservations", type=['csv'])

st.divider()

# --- Functions ---
def map_fy_chk(fy_value):
    val = str(fy_value).strip() 
    if val in ['Q1 FY24-25', 'Q2 FY24-25', 'Q3 FY24-25', 'Q4 FY24-25', 'Q4 FY23-24']:
        return 'FY 2024-25'
    elif val == 'Q1 FY25-26':
        return 'Q1'
    elif val == 'Q2 FY25-26':
        return 'Q2'
    elif val == 'Q3 FY25-26':
        return 'Q3'
    elif val == 'Q4 FY25-26':
        return 'Q4'
    elif val == 'Q1 FY26-27':
        return 'Q1_26-27'
    else:
        return ""

def read_csv_safely(uploaded_file):
    encodings = ['utf-8', 'cp1252', 'latin1', 'iso-8859-1']
    for enc in encodings:
        try:
            uploaded_file.seek(0) 
            df = pd.read_csv(uploaded_file, encoding=enc)
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode the CSV file. Please check the file format.")

ILLEGAL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')

def clean_text(val):
    if isinstance(val, str):
        return ILLEGAL_CHARS_RE.sub('', val).strip()
    return val

def map_validation_m(val):
    if pd.isna(val):
        return ""
    val_str = str(val).strip()
    s_lower = val_str.lower()
    
    if 'overdue' in s_lower:
        return 'Overdue'
    elif 'not due' in s_lower:
        return 'Not Due'
    elif 'remediated' in s_lower and 'pending validation' in s_lower:
        return 'Remediated and Pending validation' 
    elif 'pending validation' in s_lower:
        return 'Remediated and Pending validation'
    elif 'remediated' in s_lower and 'validated' in s_lower:
        return 'Remediated and Validated'
    elif 'validated' in s_lower:
        return 'Remediated and Validated'
    else:
        return val_str

def extract_highest_date(val):
    if pd.isna(val) or str(val).strip() == "":
        return "Timeline not available"
    text = str(val)
    date_pattern = r'\b(?:\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}|\d{1,2}[\s.-]+[A-Za-z]{3,9}[\s.-]+\d{2,4})\b'
    matches = re.findall(date_pattern, text)
    if not matches:
        return "Timeline not available"
    valid_dates = []
    for match in matches:
        try:
            dt = pd.to_datetime(match, dayfirst=True)
            valid_dates.append(dt)
        except Exception:
            pass 
    if valid_dates:
        max_dt = max(valid_dates)
        return max_dt.strftime('%d-%b-%Y') 
    else:
        return "Timeline not available"

# --- Processing Logic ---
if st.button("Process, Merge Files and Generate Dashboard", type="primary", use_container_width=True):
    
    files_to_process = [
        (file1, 'Completed-Observation'),
        (file2, 'Open-Observation'),
        (file3, 'PendingApprovalObservations')
    ]
    
    processed_dfs = []
    
    with st.status("Processing files...", expanded=True) as status:
        for uploaded_file, source_name in files_to_process:
            if uploaded_file is not None:
                st.write(f"Reading and formatting: {source_name}...")
                try:
                    df = read_csv_safely(uploaded_file)
                    df.columns = [clean_text(str(c)) for c in df.columns]
                    df = df.dropna(how='all').dropna(axis=1, how='all')
                    try:
                        df = df.map(clean_text)
                    except AttributeError:
                        df = df.applymap(clean_text)
                    df['File source'] = source_name
                    processed_dfs.append(df)
                except Exception as e:
                    st.error(f"Error processing {source_name}: {e}")
            else:
                st.warning(f"⚠️ {source_name} was not uploaded. It will be skipped.")

        if processed_dfs:
            st.write("Merging files, renaming column, and applying FY_chk mapping...")
            cumulative_df = pd.concat(processed_dfs, ignore_index=True)
            
            if 'FY' in cumulative_df.columns:
                cumulative_df.rename(columns={'FY': 'Quarter Reported'}, inplace=True)
            if 'Quarter Reported' in cumulative_df.columns:
                cumulative_df['FY_chk'] = cumulative_df['Quarter Reported'].apply(map_fy_chk)
            else:
                st.warning("Column 'Quarter Reported' (formerly 'FY') not found. 'FY_chk' column cannot be populated.")
            
            st.write("Calculating Unique Count & applying overrides...")
            required_cols = ['FY_chk', 'Audit Area', 'Observation Title']
            missing_cols = [col for col in required_cols if col not in cumulative_df.columns]
            
            if not missing_cols:
                # Find Unique Observation Column early
                obs_col_name = next((col for col in cumulative_df.columns if 'unique observation' in col.lower()), None)
                
                if obs_col_name:
                    obs_series = cumulative_df[obs_col_name].astype(str).str.strip().str.replace('.0', '', regex=False)
                    
                    # 🔴 FILTER OUT 1166 and 1167 rows immediately 🔴
                    mask_to_keep = ~obs_series.isin(['1166', '1167'])
                    cumulative_df = cumulative_df[mask_to_keep].reset_index(drop=True)
                    obs_series = obs_series[mask_to_keep].reset_index(drop=True)
                
                # Now calculate Unique Counts with filtered dataframe
                group_counts = cumulative_df.groupby(required_cols, dropna=False)['FY_chk'].transform('size')
                cumulative_df['Unique Count'] = 1.0 / group_counts
                
                if obs_col_name:
                    zero_count_ids = [
                        '1189', '1168', '759', '354', '353', '137', '136', '135', '1165', '1164', '1163', '771', '757', '717', '698'
                    ]
                    mask_zero = obs_series.isin(zero_count_ids)
