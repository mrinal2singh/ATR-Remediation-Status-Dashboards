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

            st.write("Calculating Near Due timelines...")
            today_date = pd.to_datetime('today').normalize()
            
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
                    '1228': 'Remediated and Pending validation',
                    '1226': 'Remediated and Pending validation',
                    '1224': 'Remediated and Pending validation',
                    '1219': 'Remediated and Pending validation',
                    '1218': 'Remediated and Pending validation',
                    '1217': 'Remediated and Pending validation',
                    '1216': 'Remediated and Pending validation',
                    '1215': 'Remediated and Pending validation',
                    '1214': 'Remediated and Pending validation',
                    '1210': 'Remediated and Pending validation',
                    '1198': 'Remediated and Pending validation',
                    '1193': 'Remediated and Pending validation',
                    '1180': 'Remediated and Pending validation',
                    '1175': 'Remediated and Pending validation',
                    '1144': 'Remediated and Pending validation',
                    '1120': 'Remediated and Pending validation',
                    '1111': 'Remediated and Pending validation',
                    '1104': 'Remediated and Pending validation',
                    '1093': 'Remediated and Pending validation',
                    '1073': 'Remediated and Pending validation',
                    '1062': 'Remediated and Pending validation',
                    '1041': 'Remediated and Validated',
                    '1040': 'Remediated and Validated',
                    '976': 'Remediated and Pending validation',
                    '951': 'Remediated and Pending validation',
                    '841': 'Remediated and Pending validation',
                    '837': 'Remediated and Pending validation',
                    '751': 'Remediated and Pending validation',
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
                    '1258': 'Garima', '1257': 'Garima', '1229': 'Jatin', '1213': 'Mrinal', '1148': 'Garima', '1147': 'Garima', '1142': 'Garima', 
                    '1137': 'Garima', '1133': 'Garima', '1129': 'Garima', '1128': 'Garima', '1126': 'Garima', '1125': 'Garima', '1124': 'Garima', 
                    '1119': 'Garima', '1118': 'Garima', '1116': 'Garima', '1113': 'Garima', '1103': 'Garima', '1102': 'Garima', '1101': 'Garima', 
                    '1099': 'Garima', '1098': 'Garima', '1097': 'Garima', '1079': 'Garima', '1078': 'Garima', '1076': 'Garima', '1071': 'Validated', 
                    '1066': 'Sameeksha', '967': 'Garima', '963': 'Garima', '958': 'Garima', '955': 'Validated', '949': 'Garima', '947': 'Garima', 
                    '838': 'Validated', '769': 'Mrinal', '757': 'Garima', '717': 'Validated', '706': 'Validated', '698': 'Shakti Singh', '685': 'Garima', 
                    '684': 'Garima', '682': 'Validated', '520': 'Oshin', '519': 'Oshin', '518': 'Oshin', '517': 'Validated', '514': 'Validated', 
                    '446': 'Validated', '443': 'Validated', '390': 'Validated', '389': 'Validated', '388': 'Validated', '387': 'Validated', '380': 'Oshin', 
                    '379': 'Oshin', '378': 'Oshin', '376': 'Validated', '373': 'Validated', '199': 'Muskan', '197': 'Muskan', '196': 'Validated', 
                    '195': 'Validated', '174': 'Muskan', '173': 'Muskan', '89': 'Validated', '46': 'Muskan', '1027': 'Validated', '1026': 'Validated', 
                    '1025': 'Validated', '1024': 'Validated', '1023': 'Validated', '1022': 'Validated', '1021': 'Validated', '1020': 'Validated', 
                    '1019': 'Validated', '1018': 'Validated', '1017': 'Validated', '1016': 'Validated', '1015': 'Validated', '1014': 'Validated', 
                    '1013': 'Validated', '1012': 'Validated', '1011': 'Validated', '1010': 'Validated', '1009': 'Validated', '1008': 'Validated', 
                    '1007': 'Validated', '1006': 'Validated', '1005': 'Validated', '1004': 'Validated', '1003': 'Validated', '1002': 'Validated', 
                    '1001': 'Validated', '1000': 'Validated', '999': 'Validated', '998': 'Validated', '997': 'Validated', '996': 'Validated', 
                    '995': 'Validated', '994': 'Validated', '993': 'Validated', '992': 'Validated', '991': 'Validated', '990': 'Validated', 
                    '989': 'Validated', '988': 'Validated', '987': 'Validated', '986': 'Validated', '985': 'Validated', '984': 'Validated', 
                    '983': 'Validated', '982': 'Validated', '981': 'Validated', '980': 'Validated', '979': 'Validated', '978': 'Validated', 
                    '965': 'Validated', '962': 'Validated', '959': 'Validated', '953': 'Validated', '950': 'Validated', '948': 'Validated', 
                    '946': 'Validated', '945': 'Validated', '944': 'Validated', '943': 'Validated', '942': 'Validated', '941': 'Validated', 
                    '940': 'Validated', '938': 'Validated', '937': 'Validated', '936': 'Validated', '935': 'Validated', '934': 'Validated', 
                    '933': 'Validated', '932': 'Validated', '931': 'Validated', '930': 'Validated', '929': 'Validated', '865': 'Muskan', 
                    '864': 'Validated', '863': 'Validated', '859': 'Validated', '858': 'Validated', '857': 'Validated', '856': 'Validated', 
                    '855': 'Validated', '854': 'Validated', '853': 'Validated', '852': 'Validated', '851': 'Validated', '850': 'Validated', 
                    '849': 'Validated', '848': 'Validated', '847': 'Validated', '846': 'Validated', '845': 'Validated', '844': 'Validated', 
                    '842': 'Validated', '839': 'Validated', '833': 'Validated', '785': 'Validated', '784': 'Validated', '783': 'Validated', 
                    '782': 'Validated', '781': 'Validated', '767': 'Validated', '766': 'Validated', '765': 'Validated', '764': 'Validated', 
                    '763': 'Validated', '762': 'Validated', '761': 'Validated', '760': 'Validated', '759': 'Validated', '756': 'Validated', 
                    '754': 'Validated', '753': 'Validated', '752': 'Validated', '750': 'Validated', '734': 'Validated', '733': 'Validated', 
                    '732': 'Validated', '730': 'Muskan', '728': 'Validated', '727': 'Validated', '710': 'Validated', '709': 'Validated', 
                    '708': 'Validated', '707': 'Validated', '704': 'Validated', '703': 'Validated', '701': 'Validated', '699': 'Validated', 
                    '697': 'Validated', '695': 'Validated', '693': 'Validated', '692': 'Validated', '683': 'Muskan', '678': 'Validated', 
                    '672': 'Validated', '670': 'Validated', '669': 'Validated', '668': 'Validated', '667': 'Validated', '666': 'Validated', 
                    '665': 'Validated', '664': 'Validated', '661': 'Validated', '660': 'Validated', '659': 'Validated', '658': 'Validated', 
                    '657': 'Validated', '656': 'Validated', '655': 'Validated', '654': 'Validated', '653': 'Validated', '652': 'Validated', 
                    '651': 'Validated', '650': 'Validated', '649': 'Validated', '648': 'Validated', '647': 'Validated', '646': 'Validated', 
                    '645': 'Validated', '643': 'Muskan', '642': 'Validated', '641': 'Validated', '640': 'Validated', '639': 'Validated', 
                    '638': 'Validated', '637': 'Validated', '636': 'Validated', '635': 'Validated', '634': 'Validated', '633': 'Validated', 
                    '632': 'Validated', '631': 'Validated', '630': 'Validated', '629': 'Validated', '628': 'Validated', '627': 'Validated', 
                    '626': 'Validated', '625': 'Validated', '624': 'Validated', '623': 'Validated', '622': 'Validated', '621': 'Validated', 
                    '620': 'Validated', '619': 'Validated', '618': 'Validated', '617': 'Validated', '616': 'Validated', '615': 'Validated', 
                    '614': 'Validated', '613': 'Validated', '612': 'Validated', '611': 'Validated', '610': 'Validated', '609': 'Validated', 
                    '608': 'Validated', '607': 'Validated', '606': 'Validated', '605': 'Validated', '604': 'Validated', '603': 'Validated', 
                    '602': 'Validated', '601': 'Validated', '600': 'Validated', '599': 'Validated', '598': 'Validated', '597': 'Validated', 
                    '596': 'Validated', '595': 'Validated', '594': 'Validated', '593': 'Validated', '592': 'Validated', '591': 'Validated', 
                    '590': 'Validated', '589': 'Validated', '588': 'Validated', '587': 'Validated', '586': 'Validated', '585': 'Validated', 
                    '584': 'Validated', '583': 'Validated', '582': 'Validated', '581': 'Validated', '580': 'Validated', '579': 'Validated', 
                    '578': 'Validated', '577': 'Validated', '576': 'Validated', '575': 'Validated', '574': 'Validated', '573': 'Validated', 
                    '572': 'Validated', '571': 'Validated', '570': 'Validated', '569': 'Validated', '568': 'Validated', '567': 'Validated', 
                    '566': 'Validated', '565': 'Validated', '564': 'Validated', '563': 'Validated', '562': 'Validated', '561': 'Validated', 
                    '560': 'Validated', '559': 'Validated', '558': 'Validated', '557': 'Validated', '556': 'Validated', '555': 'Validated', 
                    '554': 'Validated', '553': 'Validated', '552': 'Validated', '551': 'Garima', '549': 'Validated', '548': 'Validated', 
                    '545': 'Validated', '544': 'Validated', '543': 'Validated', '542': 'Validated', '541': 'Validated', '540': 'Validated', 
                    '539': 'Validated', '538': 'Validated', '537': 'Validated', '536': 'Validated', '535': 'Validated', '534': 'Validated', 
                    '533': 'Validated', '532': 'Validated', '531': 'Validated', '530': 'Validated', '529': 'Validated', '528': 'Validated', 
                    '527': 'Validated', '526': 'Validated', '525': 'Validated', '524': 'Validated', '523': 'Validated', '522': 'Validated', 
                    '521': 'Validated', '516': 'Validated', '515': 'Validated', '513': 'Validated', '512': 'Validated', '511': 'Validated', 
                    '510': 'Validated', '509': 'Validated', '508': 'Validated', '507': 'Validated', '506': 'Validated', '505': 'Validated', 
                    '504': 'Validated', '503': 'Validated', '502': 'Validated', '501': 'Validated', '500': 'Validated', '499': 'Validated', 
                    '498': 'Validated', '497': 'Validated', '496': 'Validated', '495': 'Validated', '494': 'Validated', '493': 'Validated', 
                    '492': 'Validated', '491': 'Validated', '490': 'Validated', '489': 'Validated', '488': 'Validated', '487': 'Validated', 
                    '486': 'Validated', '485': 'Validated', '484': 'Validated', '483': 'Validated', '482': 'Validated', '481': 'Validated', 
                    '480': 'Validated', '479': 'Validated', '478': 'Validated', '477': 'Validated', '476': 'Validated', '475': 'Validated', 
                    '474': 'Validated', '473': 'Validated', '472': 'Validated', '471': 'Validated', '470': 'Validated', '469': 'Validated', 
                    '468': 'Validated', '467': 'Validated', '466': 'Validated', '465': 'Validated', '464': 'Validated', '463': 'Validated', 
                    '462': 'Validated', '461': 'Validated', '460': 'Validated', '459': 'Validated', '458': 'Validated', '457': 'Validated', 
                    '456': 'Validated', '455': 'Validated', '454': 'Validated', '453': 'Validated', '452': 'Validated', '451': 'Validated', 
                    '450': 'Validated', '449': 'Validated', '448': 'Validated', '447': 'Validated', '445': 'Validated', '444': 'Validated', 
                    '442': 'Validated', '441': 'Validated', '440': 'Validated', '439': 'Validated', '438': 'Validated', '437': 'Validated', 
                    '436': 'Validated', '435': 'Validated', '434': 'Validated', '433': 'Validated', '432': 'Validated', '431': 'Validated', 
                    '430': 'Validated', '429': 'Validated', '428': 'Validated', '427': 'Validated', '426': 'Validated', '425': 'Validated', 
                    '424': 'Validated', '423': 'Validated', '422': 'Validated', '421': 'Validated', '420': 'Validated', '419': 'Validated', 
                    '418': 'Validated', '417': 'Validated', '416': 'Validated', '415': 'Validated', '414': 'Validated', '413': 'Validated', 
                    '412': 'Validated', '411': 'Validated', '410': 'Validated', '409': 'Validated', '408': 'Validated', '407': 'Validated', 
                    '406': 'Validated', '405': 'Validated', '404': 'Validated', '403': 'Validated', '402': 'Validated', '401': 'Validated', 
                    '400': 'Validated', '399': 'Validated', '398': 'Validated', '397': 'Validated', '396': 'Validated', '395': 'Validated', 
                    '394': 'Validated', '393': 'Validated', '392': 'Validated', '391': 'Validated', '386': 'Validated', '385': 'Validated', 
                    '384': 'Validated', '383': 'Validated', '382': 'Validated', '381': 'Validated', '377': 'Validated', '375': 'Validated', 
                    '374': 'Validated', '372': 'Validated', '371': 'Validated', '370': 'Validated', '369': 'Validated', '368': 'Validated', 
                    '367': 'Validated', '366': 'Validated', '365': 'Validated', '364': 'Validated', '363': 'Validated', '362': 'Validated', 
                    '361': 'Validated', '360': 'Validated', '359': 'Validated', '358': 'Validated', '357': 'Validated', '356': 'Validated', 
                    '355': 'Validated', '354': 'Validated', '353': 'Validated', '352': 'Validated', '351': 'Validated', '350': 'Validated', 
                    '349': 'Validated', '348': 'Validated', '347': 'Validated', '346': 'Validated', '345': 'Validated', '344': 'Validated', 
                    '343': 'Validated', '342': 'Validated', '341': 'Validated', '340': 'Validated', '339': 'Validated', '338': 'Validated', 
                    '337': 'Validated', '336': 'Validated', '335': 'Validated', '334': 'Validated', '333': 'Validated', '332': 'Validated', 
                    '331': 'Validated', '330': 'Validated', '329': 'Validated', '328': 'Validated', '327': 'Validated', '326': 'Validated', 
                    '325': 'Validated', '324': 'Validated', '323': 'Validated', '322': 'Validated', '321': 'Validated', '320': 'Validated', 
                    '319': 'Validated', '318': 'Validated', '317': 'Validated', '316': 'Validated', '315': 'Validated', '314': 'Validated', 
                    '313': 'Validated', '312': 'Validated', '311': 'Validated', '310': 'Validated', '309': 'Validated', '308': 'Validated', 
                    '307': 'Validated', '281': 'Validated', '280': 'Validated', '279': 'Muskan', '278': 'Muskan', '276': 'Validated', 
                    '274': 'Validated', '273': 'Validated', '269': 'Validated', '268': 'Validated', '267': 'Validated', '266': 'Validated', 
                    '265': 'Validated', '264': 'Validated', '263': 'Validated', '262': 'Validated', '261': 'Validated', '260': 'Validated', 
                    '259': 'Validated', '258': 'Validated', '257': 'Validated', '256': 'Validated', '255': 'Validated', '254': 'Validated', 
                    '253': 'Validated', '252': 'Validated', '251': 'Validated', '250': 'Validated', '249': 'Validated', '248': 'Validated', 
                    '247': 'Validated', '246': 'Validated', '245': 'Validated', '244': 'Validated', '243': 'Validated', '242': 'Validated', 
                    '241': 'Validated', '240': 'Validated', '238': 'Validated', '237': 'Validated', '236': 'Validated', '235': 'Validated', 
                    '234': 'Validated', '233': 'Validated', '232': 'Validated', '231': 'Validated', '230': 'Validated', '229': 'Validated', 
                    '228': 'Validated', '227': 'Validated', '226': 'Validated', '225': 'Validated', '224': 'Validated', '223': 'Validated', 
                    '222': 'Validated', '221': 'Validated', '220': 'Validated', '219': 'Validated', '218': 'Validated', '217': 'Validated', 
                    '216': 'Validated', '215': 'Validated', '214': 'Validated', '213': 'Validated', '212': 'Muskan', '211': 'Validated', 
                    '210': 'Validated', '209': 'Validated', '208': 'Validated', '207': 'Validated', '206': 'Validated', '205': 'Validated', 
                    '204': 'Validated', '203': 'Validated', '202': 'Validated', '201': 'Validated', '200': 'Validated', '198': 'Validated', 
                    '194': 'Validated', '193': 'Validated', '192': 'Validated', '191': 'Validated', '190': 'Validated', '189': 'Validated', 
                    '188': 'Validated', '187': 'Validated', '186': 'Validated', '185': 'Validated', '184': 'Validated', '183': 'Validated', 
                    '182': 'Validated', '181': 'Validated', '180': 'Validated', '179': 'Validated', '178': 'Validated', '177': 'Validated', 
                    '176': 'Validated', '175': 'Validated', '172': 'Validated', '171': 'Validated', '170': 'Validated', '169': 'Validated', 
                    '168': 'Validated', '167': 'Validated', '166': 'Validated', '165': 'Validated', '164': 'Validated', '163': 'Validated', 
                    '162': 'Validated', '161': 'Validated', '160': 'Validated', '159': 'Validated', '158': 'Validated', '157': 'Validated', 
                    '156': 'Validated', '155': 'Validated', '154': 'Validated', '153': 'Validated', '152': 'Validated', '151': 'Validated', 
                    '150': 'Validated', '149': 'Validated', '148': 'Validated', '147': 'Validated', '146': 'Validated', '145': 'Validated', 
                    '144': 'Validated', '143': 'Validated', '142': 'Validated', '141': 'Validated', '140': 'Validated', '139': 'Validated', 
                    '138': 'Validated', '137': 'Validated', '136': 'Validated', '135': 'Validated', '134': 'Validated', '133': 'Validated', 
                    '132': 'Validated', '131': 'Validated', '130': 'Validated', '129': 'Validated', '128': 'Validated', '127': 'Validated', 
                    '126': 'Validated', '125': 'Validated', '124': 'Validated', '123': 'Validated', '122': 'Validated', '121': 'Validated', 
                    '120': 'Validated', '119': 'Validated', '118': 'Validated', '117': 'Validated', '116': 'Validated', '115': 'Validated', 
                    '114': 'Validated', '113': 'Validated', '112': 'Validated', '111': 'Validated', '110': 'Validated', '109': 'Validated', 
                    '108': 'Validated', '107': 'Validated', '106': 'Validated', '105': 'Validated', '104': 'Validated', '103': 'Validated', 
                    '102': 'Validated', '101': 'Validated', '100': 'Validated', '99': 'Validated', '98': 'Validated', '97': 'Validated', 
                    '96': 'Validated', '95': 'Validated', '94': 'Validated', '93': 'Validated', '92': 'Validated', '91': 'Validated', 
                    '90': 'Validated', '88': 'Validated', '87': 'Validated', '86': 'Validated', '85': 'Validated', '84': 'Validated', 
                    '83': 'Validated', '82': 'Validated', '81': 'Validated', '80': 'Validated', '79': 'Validated', '78': 'Validated', 
                    '77': 'Validated', '76': 'Validated', '75': 'Validated', '74': 'Validated', '73': 'Validated', '72': 'Validated', 
                    '71': 'Validated', '70': 'Validated', '69': 'Validated', '68': 'Validated', '67': 'Validated', '66': 'Validated', 
                    '65': 'Validated', '64': 'Validated', '63': 'Validated', '62': 'Garima', '61': 'Garima', '60': 'Validated', 
                    '59': 'Validated', '58': 'Validated', '57': 'Validated', '56': 'Validated', '55': 'Validated', '54': 'Validated', 
                    '53': 'Validated', '52': 'Validated', '51': 'Validated', '50': 'Validated', '49': 'Validated', '48': 'Validated', 
                    '47': 'Validated', '45': 'Validated', '44': 'Validated', '43': 'Validated', '42': 'Validated', '41': 'Validated', 
                    '40': 'Validated', '39': 'Validated', '38': 'Validated', '37': 'Validated', '36': 'Validated', '35': 'Validated', 
                    '34': 'Validated', '33': 'Validated', '32': 'Validated', '31': 'Validated', '30': 'Validated', '29': 'Validated', 
                    '28': 'Validated', '27': 'Validated', '26': 'Validated', '25': 'Validated', '24': 'Validated', '23': 'Validated', 
                    '22': 'Validated', '21': 'Validated', '20': 'Validated', '19': 'Validated', '18': 'Validated', '17': 'Validated', 
                    '16': 'Validated', '15': 'Validated', '14': 'Validated', '13': 'Validated', '12': 'Validated', '11': 'Validated', 
                    '10': 'Validated', '9': 'Validated', '8': 'Validated', '7': 'Validated', '6': 'Validated', '5': 'Validated', 
                    '4': 'Validated', '2': 'Validated', '1': 'Validated', '1312': 'Muskan', '1311': 'Muskan', '1268': 'Sameeksha', 
                    '1267': 'Sameeksha', '1266': 'Sameeksha', '1265': 'Sameeksha', '1264': 'Sameeksha', '1256': 'Muskan', '1255': 'Muskan', 
                    '1254': 'Muskan', '1253': 'Muskan', '1251': 'Jatin', '1250': 'Jatin', '1249': 'Jatin', '1248': 'Jatin', '1247': 'Jatin', 
                    '1246': 'Jatin', '1245': 'Jatin', '1244': 'Jatin', '1242': 'Jatin', '1241': 'Jatin', '1240': 'Jatin', '1239': 'Jatin', 
                    '1238': 'Jatin', '1237': 'Jatin', '1236': 'Jatin', '1228': 'Jatin', '1226': 'Jatin', '1225': 'Jatin', '1224': 'Jatin', 
                    '1223': 'Jatin', '1221': 'Jatin', '1219': 'Jatin', '1218': 'Mrinal', '1217': 'Mrinal', '1216': 'Mrinal', '1215': 'Mrinal', 
                    '1214': 'Mrinal', '1212': 'Mrinal', '1211': 'Garima', '1210': 'Garima', '1209': 'Muskan', '1207': 'Muskan', '1206': 'Muskan', 
                    '1203': 'Muskan', '1202': 'Muskan', '1198': 'Muskan', '1197': 'Muskan', '1193': 'Muskan', '1180': 'Muskan', '1175': 'Muskan', 
                    '1165': 'Muskan', '1164': 'Muskan', '1163': 'Muskan', '1162': 'Sameeksha', 
                    '1161': 'Sameeksha', '1160': 'Sameeksha', '1159': 'Sameeksha', '1158': 'Sameeksha', '1157': 'Sameeksha', '1156': 'Sameeksha', 
                    '1155': 'Sameeksha', '1154': 'Sameeksha', '1153': 'Sameeksha', '1152': 'Sameeksha', '1151': 'Sameeksha', '1144': 'Garima', 
                    '1120': 'Jatin', '1115': 'Shakti Singh', '1112': 'Shakti Singh', '1111': 'Jatin', '1110': 'Shakti Singh', '1104': 'Jatin', 
                    '1096': 'Garima', '1093': 'Jatin', '1090': 'Shakti Singh', '1075': 'Garima', '1073': 'Muskan', '1062': 'Muskan', 
                    '1061': 'Muskan', '1058': 'Muskan', '1056': 'Sameeksha', '1041': 'Pankaj', '1040': 'Pankaj', '1039': 'Mrinal', 
                    '977': 'Garima', '976': 'Garima', '975': 'Garima', '974': 'Garima', '973': 'Muskan', '972': 'Garima', '971': 'Garima', 
                    '970': 'Garima', '968': 'Garima', '966': 'Garima', '964': 'Garima', '961': 'Garima', '960': 'Garima', '957': 'Garima', 
                    '956': 'Garima', '954': 'Garima', '952': 'Garima', '951': 'Garima', '939': 'Muskan', '928': 'Sameeksha', '927': 'Sameeksha', 
                    '926': 'Sameeksha', '925': 'Sameeksha', '924': 'Sameeksha', '923': 'Sameeksha', '922': 'Sameeksha', '921': 'Sameeksha', 
                    '920': 'Sameeksha', '919': 'Sameeksha', '918': 'Sameeksha', '917': 'Sameeksha', '916': 'Sameeksha', '915': 'Sameeksha', 
                    '914': 'Sameeksha', '913': 'Sameeksha', '912': 'Sameeksha', '843': 'Oshin', '841': 'Oshin', '840': 'Oshin', '837': 'Oshin', 
                    '836': 'Oshin', '835': 'Oshin', '834': 'Oshin', '771': 'Mrinal', '770': 'Mrinal', '768': 'Mrinal', '755': 'Muskan', 
                    '751': 'Muskan', '731': 'Muskan', '729': 'Muskan', '705': 'Oshin', '702': 'Mrinal', '700': 'Mrinal', '694': 'Muskan', 
                    '691': 'Mrinal', '690': 'Mrinal', '689': 'Muskan', '688': 'Mrinal', '687': 'Mrinal', '680': 'Shakti Singh', '679': 'Shakti Singh', 
                    '677': 'Shakti Singh', '676': 'Shakti Singh', '675': 'Shakti Singh', '674': 'Shakti Singh', '673': 'Shakti Singh', 
                    '671': 'Shakti Singh', '663': 'Muskan', '644': 'Muskan', '550': 'Garima', '547': 'Garima', '546': 'Garima', '291': 'Garima', 
                    '271': 'Shakti Singh', '239': 'Muskan', '3': 'Muskan'
                }
                cumulative_df['Allocated'] = obs_series.map(allocation_mapping).fillna('Unallocated')
                
                # Further dynamic replace for specific names if they seep into datasets
                cumulative_df['Allocated'] = cumulative_df['Allocated'].replace({
                    'Yogesh Pundir': 'Muskan', 
                    'Mukul Tyagi': 'Garima',
                    'Mukul': 'Garima'
                })
            else:
                st.warning("Could not find 'Unique observation No' to map Allocations.")
                cumulative_df['Allocated'] = 'Unallocated'

            st.write("Applying final Team overrides...")
            mask = (cumulative_df['Allocated'].str.strip().str.lower() == 'sameeksha') & \
                   (cumulative_df['Team'].str.strip().str.lower() == 'in house')
            cumulative_df.loc[mask, 'Team'] = 'IT Team'

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                cumulative_df.to_excel(writer, index=False)
            
            # Save to Local File and Session State for auto-populate feature
            cumulative_df.to_pickle(LAST_RUN_FILE)
            st.session_state['cumulative_df'] = cumulative_df
            
            status.update(label="✅ Processing Complete!", state="complete", expanded=False)
            st.success("Files successfully merged, sanitized, and updated with Team & Allocation mapping!")
            
            st.download_button(
                label="📥 Download LARS Cumulative.xlsx",
                data=output.getvalue(),
                file_name="LARS Cumulative.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
        else:
            status.update(label="❌ No files to process", state="error")
            st.error("Please upload at least one file to process.")
            
# --- DASHBOARD GENERATION ---
if st.session_state['cumulative_df'] is not None:
    cumulative_df = st.session_state['cumulative_df']
    
    st.divider()
    st.header("📈 Dashboard")
    
    # --- ROW 1: Donut Charts ---
    chart_col1, chart_col2, chart_col3 = st.columns(3)

    with chart_col1:
        status_counts = cumulative_df.groupby('Validation(M)')['Unique Count'].sum().reset_index()
        if not status_counts.empty and status_counts['Unique Count'].sum() > 0:
            fig1 = px.pie(status_counts, values='Unique Count', names='Validation(M)', hole=0.5, title='Overall Status Distribution')
            fig1.update_traces(textposition='inside', textinfo='percent+label')
            # Updated height to 280 to reduce chart size
            fig1.update_layout(showlegend=False, margin=dict(t=40, b=10, l=10, r=10), title_x=0.5, height=280)
            st.plotly_chart(fig1, use_container_width=True)

    with chart_col2:
        overdue_counts = cumulative_df[cumulative_df['Validation(M)'].str.lower() == 'overdue'].groupby('Allocated')['Unique Count'].sum().reset_index()
        if not overdue_counts.empty and overdue_counts['Unique Count'].sum() > 0:
            fig2 = px.pie(overdue_counts, values='Unique Count', names='Allocated', hole=0.5, title='Overdue by Allocated')
            fig2.update_traces(textposition='inside', textinfo='percent+label')
            # Updated height to 280 to reduce chart size
            fig2.update_layout(showlegend=False, margin=dict(t=40, b=10, l=10, r=10), title_x=0.5, height=280)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No Overdue Data for Chart")

    with chart_col3:
        neardue_counts = cumulative_df[cumulative_df['Validation(M)'].str.lower() == 'near due'].groupby('Allocated')['Unique Count'].sum().reset_index()
        if not neardue_counts.empty and neardue_counts['Unique Count'].sum() > 0:
            fig3 = px.pie(neardue_counts, values='Unique Count', names='Allocated', hole=0.5, title='Near Due by Allocated')
            fig3.update_traces(textposition='inside', textinfo='percent+label')
            # Updated height to 280 to reduce chart size
            fig3.update_layout(showlegend=False, margin=dict(t=40, b=10, l=10, r=10), title_x=0.5, height=280)
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("No Near Due Data for Chart")

    st.divider()

    # --- ROW 2: Pivot Tables ---
    fy_cols = ['FY 2024-25', 'Q1', 'Q2', 'Q3', 'Q4']
    deep_blue = "#002060" # Updated to Deep Blue
    
    header_styles = [{
        'selector': 'th',
        'props': [
            ('background-color', deep_blue), 
            ('color', 'white'), 
            ('font-weight', 'bold'),
            ('font-size', '13px'),
            ('padding', '4px 8px')
        ]
    }]
    
    def style_totals_row(row):
        is_total = False
        if hasattr(row, 'name'):
            if isinstance(row.name, tuple):
                if 'Total' in str(row.name[0]): is_total = True
            elif 'Total' in str(row.name): is_total = True
        
        if 'Allocated' in row.index and 'Total' in str(row['Allocated']):
            is_total = True
            
        if is_total:
            return [f'background-color: {deep_blue}; color: white; font-weight: bold; font-size: 12px; padding: 4px;'] * len(row)
        return [''] * len(row)

    def apply_global_table_styles(styler_obj):
        return styler_obj.set_properties(**{'font-size': '12px', 'padding': '4px 6px'})\
                         .set_table_styles(header_styles)

    def create_summary_pivot(df, status_filter):
        f_df = df[df['Validation(M)'].str.lower() == status_filter.lower()]
        pt = pd.pivot_table(f_df, values='Unique Count', index=['Team', 'Allocated'], columns='FY_chk', aggfunc='sum', fill_value=0)
        pt = pt.reindex(columns=fy_cols, fill_value=0)
        
        all_combos = df[['Team', 'Allocated']].drop_duplicates().set_index(['Team', 'Allocated'])
        pt = all_combos.join(pt, how='left').fillna(0)
        pt['Total'] = pt.sum(axis=1)
        
        pt.loc[('Total', ''), :] = pt.sum(axis=0, numeric_only=True)
        pt.fillna('', inplace=True) 
        pt = pt.sort_index(level='Team', na_position='last')
        return pt

    def create_details_table(df, status_filter):
        f_df = df[df['Validation(M)'].str.lower() == status_filter.lower()]
        if f_df.empty: return pd.DataFrame()
        
        f_df = f_df.sort_values(by=['Allocated', 'Audit Area', 'Observation Title'])
        rows_list = []
        
        for allocated, group1 in f_df.groupby('Allocated', sort=False):
            alloc_total = group1['Unique Count'].sum()
            for audit_area, group2 in group1.groupby('Audit Area', sort=False):
                for obs_title, group3 in group2.groupby('Observation Title', sort=False):
                    obs_total = group3['Unique Count'].sum()
                    rows_list.append({
                        'Allocated': allocated, 'Audit Area': audit_area,
                        'Observation Title': obs_title, 'Total': obs_total
                    })
            rows_list.append({
                'Allocated': f'{allocated} Total', 'Audit Area': '',
                'Observation Title': '', 'Total': alloc_total
            })
            
        grand_total = f_df['Unique Count'].sum()
        rows_list.append({
            'Allocated': 'Total', 'Audit Area': '', 'Observation Title': '', 'Total': grand_total
        })
        return pd.DataFrame(rows_list)

    col_sum, col_overdue, col_near = st.columns(3)
    
    with col_sum:
        st.subheader("Count of observations noted in")
        pt1 = pd.pivot_table(cumulative_df, values='Unique Count', index='Validation(M)', columns='FY_chk', aggfunc='sum', fill_value=0)
        pt1 = pt1.reindex(columns=fy_cols, fill_value=0)
        pt1['Total'] = pt1.sum(axis=1)
        
        display_rows = [
            'Remediated and Validated', 'Remediated and Pending validation', 'Remediated and Pending validation, LARS not updated',
            'Not Due', 'Date not updated in LARS', 'Near Due', 'Overdue'
        ]
        pt1 = pt1.reindex(index=display_rows, fill_value=0)
        
        total_row = pt1.sum(axis=0)
        total_row.name = 'Total observation'
        pt1 = pd.concat([pd.DataFrame([total_row]), pt1])
        
        styled_pt1 = apply_global_table_styles(pt1.style.apply(style_totals_row, axis=1)).format("{:.0f}")
        st.dataframe(styled_pt1, use_container_width=True)

    with col_overdue:
        st.subheader("Overdue Status")
        pt_overdue = create_summary_pivot(cumulative_df, "Overdue")
        styled_overdue = apply_global_table_styles(pt_overdue.style.apply(style_totals_row, axis=1)).format("{:.0f}")
        st.dataframe(styled_overdue, use_container_width=True)
        
    with col_near:
        st.subheader("Near Due Status")
        pt_near = create_summary_pivot(cumulative_df, "Near Due")
        styled_near = apply_global_table_styles(pt_near.style.apply(style_totals_row, axis=1)).format("{:.0f}")
        st.dataframe(styled_near, use_container_width=True)

    # --- ROW 3: Detailed Observation Lists ---
    st.divider()
    st.header("Detailed Observation Breakdown")
    
    dt_col1, dt_col2 = st.columns(2)
    
    with dt_col1:
        st.subheader("🚨 Overdue Details")
        overdue_details = create_details_table(cumulative_df, "Overdue")
        if not overdue_details.empty:
            styled_ov_det = apply_global_table_styles(overdue_details.style.apply(style_totals_row, axis=1)).format({'Total': '{:.1f}'})
            st.dataframe(styled_ov_det, use_container_width=True, hide_index=True)
        else:
            st.info("No Overdue items found.")

    with dt_col2:
        st.subheader("⚠️ Near Due Details")
        near_details = create_details_table(cumulative_df, "Near Due")
        if not near_details.empty:
            styled_nd_det = apply_global_table_styles(near_details.style.apply(style_totals_row, axis=1)).format({'Total': '{:.1f}'})
            st.dataframe(styled_nd_det, use_container_width=True, hide_index=True)
        else:
            st.info("No Near Due items found.")
