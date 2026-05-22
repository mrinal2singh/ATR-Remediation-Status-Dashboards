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
    if pd.isna(val)
