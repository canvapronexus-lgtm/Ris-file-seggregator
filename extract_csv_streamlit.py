import streamlit as st
import pandas as pd
import re
from io import StringIO, BytesIO

# === Streamlit setup ===
st.set_page_config(page_title="RIS File Parser Pro", layout="wide")
st.title("🔬 RIS File Parser Pro (Memory Optimized)")

st.markdown("""
Upload **one or more** `.ris` files. This tool will parse them all to extract:
- **Title** (`T1`), **Year** (`Y1`), **Journal** (`JF`/`JO`), **Keywords** (`KW`)
- **All Authors** (from all `A1` tags)
- **Corresponding Author Name** & **Email** (from `M1`, `AD`, `A1`)

This version is **memory-optimized** to work on Streamlit Cloud.
""")

# === Regex patterns ===
EMAIL_RE = re.compile(r'[\w\.-]+@[\w\.-]+\w+', re.IGNORECASE)
CORRESPONDING_AUTHOR_RE = re.compile(
    r'([^,;()]+?),\s*([\w\.-]+@[\w\.-]+\w+)', 
    re.IGNORECASE
)

# Function to clear session state
def clear_results():
    if 'processed_data_set' in st.session_state:
        del st.session_state['processed_data_set']
    st.experimental_rerun() 

# === File uploader ===
uploaded_files = st.file_uploader(
    "Upload .ris file(s)", 
    type=["ris", "txt"], 
    accept_multiple_files=True
)

if 'processed_data_set' not in st.session_state:
    st.session_state['processed_data_set'] = set()

if uploaded_files:
    
    st.session_state['processed_data_set'] = set() # Clear previous results
    
    try:
        for uploaded in uploaded_files:
            st.info(f"Processing file: `{uploaded.name}`...")
            
            text = uploaded.getvalue().decode("utf-8-sig", errors="ignore").strip()
            if not text:
                st.warning(f"Skipping empty file: `{uploaded.name}`")
                continue

            records = text.split('\nER - ')

            for record_str in records:
                if not record_str.strip():
                    continue

                # Initialize variables
                title, year, journal, first_author = None, None, None, None
                all_authors_list, keywords_list = [], []
                corresponding_info = {} 
                emails_found_in_record = set()
                
                lines = record_str.split('\n')
                full_record_text = " \n ".join(lines)
                
                for line in lines:
                    line = line.strip()
                    if ' - ' not in line: continue

                    try:
                        tag, value = [s.strip() for s in line.split(' - ', 1)]
                    except ValueError:
                        continue

                    # Extract data
                    if tag == 'T1': title = value
                    elif tag == 'Y1': year = value
                    elif tag == 'JF' or tag == 'JO': journal = value
                    elif tag == 'KW': keywords_list.append(value)
                    elif tag == 'A1':
                        author_name = value
                        all_authors_list.append(author_name)
                        if not first_author: first_author = author_name
                    
                    # Corresponding Info Logic
                    if tag == 'M1' or tag == 'AD' or tag == 'A1':
                        matches = CORRESPONDING_AUTHOR_RE.findall(line)
                        for name_part, email in matches:
                            email_clean = email.lower()
                            name = name_part.strip().replace('*', '').replace('(Corresponding Author)', '')
                            name = name.split(';')[-1].strip()
                            if email_clean not in corresponding_info:
                                corresponding_info[email_clean] = name
                            emails_found_in_record.add(email_clean)

                # Fallback email search
                all_emails_in_record = set(email.lower() for email in EMAIL_RE.findall(full_record_text))
                for email in all_emails_in_record:
                    emails_found_in_record.add(email)
                    if email not in corresponding_info:
                        corresponding_info[email] = first_author if first_author else "N/A"

                # Add data to the SET if we have a title and email
                if title and emails_found_in_record:
                    authors_str = '; '.join(all_authors_list)
                    keywords_str = '; '.join(keywords_list)
                    
                    for email in emails_found_in_record:
                        name = corresponding_info.get(email, first_author if first_author else "N/A")
                        
                        # Add a tuple to the set. Tuples are memory-efficient.
                        # This automatically handles duplicates.
                        record_tuple = (
                            title,
                            year,
                            journal,
                            name,
                            email,
                            authors_str,
                            keywords_str,
                            uploaded.name
                        )
                        st.session_state['processed_data_set'].add(record_tuple)

        # === Handle results ===
        if not st.session_state['processed_data_set']:
            st.error("❌ No records with corresponding emails were found in any of the files.")
            st.stop()

        # --- This is the key change ---
        # Only create the DataFrame *after* all processing is done.
        st.success(f"Processing complete! Found {len(st.session_state['processed_data_set'])} unique records.")
        st.info("Creating final table for display...")
        
        df = pd.DataFrame(
            list(st.session_state['processed_data_set']),
            columns=[
                'Title', 'Year', 'Journal', 'Corresponding Author', 'Email',
                'All Authors', 'Keywords', 'Source File'
            ]
        )
        
        st.dataframe(df, use_container_width=True)

        # === Download buttons ===
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download as CSV",
            data=csv_bytes,
            file_name="ris_extracted_data.csv",
            mime="text/csv",
            key="csv_download"
        )

        buf = BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        st.download_button(
            "⬇️ Download as Excel",
            data=buf,
            file_name="ris_extracted_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="excel_download"
        )

    except Exception as e:
        st.error(f"⚠️ Processing error: {e}")
        st.exception(e) # Show full error details

elif 'processed_data_set' in st.session_state and st.session_state['processed_data_set']:
    # Show a clear button if there are old results
    st.info("Results from previous upload are shown below. Upload new files to clear.")
    st.button("Clear Old Results", on_click=clear_results)
    
else:
    st.info("👆 Upload your .ris file(s) to begin.")
