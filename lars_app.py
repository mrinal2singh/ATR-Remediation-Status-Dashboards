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
                    cumulative_df.loc[mask_zero, 'Unique Count'] = 0.0
                    
                    explicit_overrides = {
                        '1129': 0.5, '1102': 0.5, '1126': 0.5, '1099': 0.5, '1124': 0.5, '1032': 0.333333, '1016': 0.333333, '999': 0.333333, '912': 0.5,
                        '1023': 0.05, '1006': 0.05, '987': 0.05, '1029': 0.05, '1028': 0.05, '1027': 0.05, '1026': 0.05, '1025': 0.05, '1024': 0.05, '1022': 0.05,
                        '1012': 0.05, '1011': 0.05, '1010': 0.05, '1009': 0.05, '1008': 0.05, '1007': 0.05, '1005': 0.05, '988': 0.05, '986': 0.05, '697': 0.5,
                        '695': 0.5, '693': 0.5, '683': 0.5, '606': 0.5, '605': 0.5, '604': 0.5, '603': 0.5, '602': 0.5, '601': 0.5, '600': 0.5, '599': 0.5, '598': 0.5,
                        '597': 0.5, '596': 0.5, '595': 0.5, '594': 0.5, '593': 0.5, '592': 0.5, '591': 0.5, '590': 0.5, '589': 0.5, '588': 0.5, '587': 0.5, '571': 0.5,
                        '570': 0.5, '569': 0.5, '562': 0.5, '561': 0.5, '560': 0.5, '559': 0.5, '552': 0.5, '459': 0.5, '450': 0.5, '449': 0.5, '448': 0.5, '447': 0.5,
                        '278': 0.5, '269': 0.5, '268': 0.5, '267': 0.5, '238': 0.5, '237': 0.5, '236': 0.5, '235': 0.5, '234': 0.5, '233': 0.5, '232': 0.5, '231': 0.5,
                        '230': 0.5, '171': 0.5, '170': 0.5, '169': 0.5, '168': 0.5, '167': 0.5, '166': 0.5, '165': 0.5, '164': 0.5, '163': 0.5, '162': 0.5, '161': 0.5,
                        '160': 0.5, '159': 0.5, '158': 0.5, '157': 0.5, '156': 0.5, '155': 0.5, '154': 0.5, '153': 0.5, '152': 0.5, '151': 0.5, '1097': 0.5, '985': 0.05,
                        '913': 0.5, '674': 0.5, '61': 1.0, '1122': 0.5, '1095': 0.5, '1128': 0.5, '1101': 0.5, '1123': 0.5, '1096': 0.5, '1125': 0.5, '1098': 0.5, '1127': 0.5, '1100': 0.5
                    }
                    for obs_id, override_val in explicit_overrides.items():
                        mask_explicit = (obs_series == obs_id)
                        cumulative_df.loc[mask_explicit, 'Unique Count'] = override_val
                else:
                    st.warning("Could not find a column containing 'Unique observation' to apply the overrides.")
            else:
                st.warning(f"Could not calculate 'Unique Count'. Missing columns: {', '.join(missing_cols)}")
            
            st.write("Applying Timeline(M) date extraction logic...")
            timeline_col = None
            for col in cumulative_df.columns:
                if 'revised timeline' in col.lower() and 'incident solution' in col.lower():
                    timeline_col = col
                    break
            if not timeline_col:
                for col in cumulative_df.columns:
                    if 'revised timeline' in col.lower():
                        timeline_col = col
                        break
            if timeline_col:
                cumulative_df['Timeline(M)'] = cumulative_df[timeline_col].apply(extract_highest_date)
            else:
                st.warning("Could not find a 'Revised Timeline' column. Populating 'Timeline(M)' with default values.")
                cumulative_df['Timeline(M)'] = "Timeline not available"

            st.write("Applying Validation(M) column logic...")
            val_status_col = next((col for col in cumulative_df.columns if 'validation status' in col.lower()), None)
            if val_status_col:
                cumulative_df['Validation(M)'] = cumulative_df[val_status_col].apply(map_validation_m)
            else:
                st.warning("Could not find a 'Validation Status' column. Skipping 'Validation(M)' creation.")
                cumulative_df['Validation(M)'] = ""
                
            st.write("Adjusting Overdue status to Not Due if Timeline >= system date...")
            today_date = pd.to_datetime('today').normalize()
            
            def correct_overdue_status(row):
                current_val = row['Validation(M)']
                if str(current_val).strip().lower() == 'overdue':
                    tl_str = str(row['Timeline(M)'])
                    if tl_str != "Timeline not available":
                        try:
                            dt = pd.to_datetime(tl_str, format='%d-%b-%Y')
                            if dt >= today_date:
                                return 'Not Due'
                        except Exception:
                            pass
                return current_val

            cumulative_df['Validation(M)'] = cumulative_df.apply(correct_overdue_status, axis=1)

            st.write("Calculating Near Due timelines...")
            
            def apply_near_due_override(row):
                current_val = row['Validation(M)']
                tl_str = str(row['Timeline(M)'])
                s_lower = str(current_val).lower()
                
                if 'remediated' in s_lower or 'closed' in s_lower or 'validated' in s_lower:
                    return current_val
                
                if tl_str != "Timeline not available":
                    try:
                        dt = pd.to_datetime(tl_str, format='%d-%b-%Y')
                        days_diff = (dt - today_date).days
                        if 0 <= days_diff <= 15:
                            return 'Near Due'
                        elif days_diff < 0:
                            return 'Overdue'
                    except Exception:
                        pass
                return current_val
                
            cumulative_df['Validation(M)'] = cumulative_df.apply(apply_near_due_override, axis=1)

            st.write("Applying explicit overrides for Validation(M)...")
            if obs_col_name:
                validation_overrides = {
                    '1228': 'Remediated and Pending validation', '1226': 'Remediated and Pending validation',
                    '1224': 'Remediated and Pending validation', '1219': 'Remediated and Pending validation',
                    '1218': 'Remediated and Pending validation', '1217': 'Remediated and Pending validation',
                    '1216': 'Remediated and Pending validation', '1215': 'Remediated and Pending validation',
                    '1214': 'Remediated and Pending validation', '1210': 'Remediated and Pending validation',
                    '1198': 'Remediated and Pending validation', '1193': 'Remediated and Pending validation',
                    '1180': 'Remediated and Pending validation', '1175': 'Remediated and Pending validation',
                    '1144': 'Remediated and Pending validation', '1120': 'Remediated and Pending validation',
                    '1111': 'Remediated and Pending validation', '1104': 'Remediated and Pending validation',
                    '1093': 'Remediated and Pending validation', '1073': 'Remediated and Pending validation',
                    '1062': 'Remediated and Pending validation', '1041': 'Remediated and Validated',
                    '1040': 'Remediated and Validated', '976': 'Remediated and Pending validation',
                    '951': 'Remediated and Pending validation', '841': 'Remediated and Pending validation',
                    '837': 'Remediated and Pending validation', '751': 'Remediated and Pending validation',
                    '949': 'Remediated and Pending validation'
                }
                for obs_id, new_val_status in validation_overrides.items():
                    mask_val_override = (obs_series == obs_id)
                    cumulative_df.loc[mask_val_override, 'Validation(M)'] = new_val_status

            st.write("Applying Team assignment logic...")
            lead_auditor_col = next((col for col in cumulative_df.columns if 'lead auditor' in col.lower()), None)
            reviewer_col = next((col for col in cumulative_df.columns if 'reviewer' in col.lower()), None)
            
            def map_team(row):
                if lead_auditor_col and pd.notna(row[lead_auditor_col]):
                    la_val = str(row[lead_auditor_col]).strip().lower()
                    deloitte_keywords = [
                        'deloitte', 'deloitte (preeti)', 'ocl ia deloitte 3 (oclia.deloitte3)',
                        'ocl ia deloitte 12 (oclia.deloitte12)', 'oclia deloitte2 (oclia.deloitte2)','oclia.deloitte16 (oclia.deloitte16)','OCL IA Deloitte 12 (oclia.deloitte12)',
                        'oclia Deloitte2 (Oclia.Deloitte2)'
                    ]
                    deloitte_keywords = [k.lower() for k in deloitte_keywords]
                    if any(keyword in la_val for keyword in deloitte_keywords): return 'Deloitte'
                if reviewer_col and pd.notna(row[reviewer_col]):
                    rev_val = str(row[reviewer_col]).strip().lower()
                    if 'sameeksha' in rev_val: return 'IT Team'
                return 'In House'

            cumulative_df['Team'] = cumulative_df.apply(map_team, axis=1)

            st.write("Applying Allocation mapping...")
            if obs_col_name: 
                allocation_mapping = {
                    '1322': 'Garima', '1321': 'Garima', '1320': 'Garima', '1319': 'Garima',
                    '1318': 'Muskan', '1317': 'Muskan', '1316': 'Muskan', '1315': 'Muskan', '1314': 'Muskan', '1313': 'Muskan',
                    '1308': 'Mrinal', '1307': 'Mrinal', '1306': 'Mrinal', '1305': 'Mrinal',
                    '1230': 'Muskan', '1227': 'Jatin', '1222': 'Jatin', '1220': 'Jatin', '1208': 'Muskan', '1200': 'Muskan', '1195': 'Validated', 
                    '1189': 'Validated', '1188': 'Validated', '1187': 'Validated', '1186': 'Validated', '1185': 'Validated', '1184': 'Validated', 
                    '1183': 'Validated', '1182': 'Validated', '1181': 'Validated', '1168': 'Validated', '1149': 'Validated', '1146': 'Validated', 
                    '1143': 'Validated', '1140': 'Validated', '1136': 'Validated', '1135': 'Validated', '1134': 'Validated', '1132': 'Validated', 
                    '1131': 'Validated', '1127': 'Validated', '1123': 'Validated', '1122': 'Validated', '1117': 'Validated', '1114': 'Validated', 
                    '1100': 'Validated', '1095': 'Validated', '1094': 'Validated', '1092': 'Validated', '1091': 'Validated', '1089': 'Validated', 
                    '1077': 'Validated', '1074': 'Validated', '1070': 'Validated', '1069': 'Validated', '1068': 'Validated', '1067': 'Validated', 
                    '1065': 'Validated', '1064': 'Validated', '1063': 'Validated', '1059': 'Muskan', '1057': 'Validated', '1055': 'Validated', 
                    '1054': 'Validated', '1053': 'Validated', '1052': 'Validated', '1051': 'Validated', '1050': 'Validated', '1049': 'Validated', 
                    '1048': 'Validated', '1047': 'Validated', '1046': 'Validated', '1045': 'Validated', '1044': 'Validated', '1043': 'Validated', 
                    '1042': 'Validated', '1038': 'Validated', '1037': 'Validated', '1036': 'Validated', '1035': 'Validated', '1033': 'Validated', 
                    '1032': 'Validated', '1031': 'Validated', '1030': 'Validated', '1029': 'Validated', '1028': 'Validated', '1301': 'Sameeksha', 
                    '1302': 'Sameeksha', '1304': 'Sameeksha', '1298': 'Sameeksha', '1303': 'Sameeksha', '1299': 'Sameeksha', '1300': 'Sameeksha', 
                    '1295': 'Sameeksha', '1294': 'Sameeksha', '1293': 'Sameeksha', '1292': 'Sameeksha', '1291': 'Sameeksha', '1290': 'Sameeksha', 
                    '1289': 'Sameeksha', '1288': 'Sameeksha', '1287': 'Sameeksha', '1286': 'Sameeksha', '1285': 'Sameeksha', '1284': 'Sameeksha', 
                    '1283': 'Sameeksha', '1282': 'Sameeksha', '1281': 'Sameeksha', '1275': 'Sameeksha', '1274': 'Sameeksha', '1273': 'Sameeksha', 
                    '1272': 'Sameeksha', '1271': 'Sameeksha', '1270': 'Sameeksha', '1269': 'Sameeksha', '1297': 'Garima', 
                    '1296': 'Garima', '1276': 'Garima', '1263': 'Garima', '1262': 'Garima', '1261': 'Garima', '1260': 'Garima', '1259': 'Garima', 
                    '1258': 'Garima', '1257': 'Garima', '1229': 'Jatin', '1213': 'Mrinal', '1148': 'Garima', '1147': 'Garima',
