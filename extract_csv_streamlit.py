import streamlit as st
import pandas as pd
import re
from io import StringIO, BytesIO

# === Streamlit setup ===
st.set_page_config(page_title="RIS File Parser Pro", layout="wide")
st.title("🔬 RIS File Parser Pro (Upgraded)")

st.markdown("""
Upload **one or more** `.ris` files. This tool will parse them all to extract:
- **Title** (`T1`), **Year** (`Y1`), **Journal** (`JF`/`JO`), **Keywords** (`KW`)
- **All Authors** (from all `A1` tags)
- **Corresponding Author Name** & **Email** (from `M1`, `AD`, `A1`)

This version has been enhanced to handle flexible spacing in RIS tags (like `T1  - `).
""")

# === Regex patterns ===
# General email regex (fallback)
EMAIL_RE = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+', re.IGNORECASE)

# New, more robust regex to find (Name, email) pairs.
# It looks for a name part (anything not a comma, semicolon, or parenthesis)
# followed by a comma, and then an email.
CORRESPONDING_AUTHOR_RE = re.compile(
    r'([^,;()]+?),\s*([\w\.-]+@[\w\.-]+\.\w+)', 
    re.IGNORECASE
)

# Function to clear session state
def clear_results():
    if 'all_parsed_data' in st.session_state:
        del st.session_state['all_parsed_data']
    # This is needed to clear the file uploader list
    st.experimental_rerun() 

# === File uploader ===
uploaded_files = st.file_uploader(
    "Upload .ris file(s)", 
    type=["ris", "txt"], 
    accept_multiple_files=True
)

if 'all_parsed_data' not in st.session_state:
    st.session_state['all_parsed_data'] = []

if uploaded_files:
    
    st.session_state['all_parsed_data'] = [] # Clear previous results on new upload
    
    try:
        for uploaded in uploaded_files:
            st.info(f"Processing file: `{uploaded.name}`...")
            
            text = uploaded.getvalue().decode("utf-8-sig", errors="ignore").strip()
            if not text:
                st.warning(f"Skipping empty or invalid file: `{uploaded.name}`")
                continue

            # Split the entire file into individual records
            records = text.split('\nER - ')

            for record_str in records:
                if not record_str.strip():
                    continue

                # Initialize variables for each record
                title, year, journal, first_author = None, None, None, None
                all_authors, keywords = [], []
                corresponding_info = {} 
                emails_found_in_record = set()
                
                lines = record_str.split('\n')
                full_record_text = " \n ".join(lines) # For broader email search
                
                for line in lines:
                    line = line.strip()
                    if ' - ' not in line: # Skip lines without the delimiter
                        continue

                    # --- Flexible Tag Parsing (THE FIX) ---
                    # Split only on the first ' - ' to get tag and value
                    try:
                        # This handles 'T1 - ', 'T1  - ', 'T1   - ', etc.
                        tag, value = [s.strip() for s in line.split(' - ', 1)]
                    except ValueError:
                        continue # Skip lines that don't split correctly

                    # Extract data based on RIS tags
                    if tag == 'T1':
                        title = value
                    elif tag == 'Y1':
                        year = value
                    elif tag == 'JF' or tag == 'JO':
                        journal = value
                    elif tag == 'KW':
                        keywords.append(value)
                    elif tag == 'A1':
                        author_name = value
                        all_authors.append(author_name)
                        if not first_author:
                            first_author = author_name # Capture the first author
                    
                    # --- Corresponding Info Logic (now more robust) ---
                    if tag == 'M1' or tag == 'AD' or tag == 'A1':
                        
                        # 1. Find explicit (Name, email) pairs
                        matches = CORRESPONDING_AUTHOR_RE.findall(line)
                        for name_part, email in matches:
                            email_clean = email.lower()
                            # Clean up the name part
                            name = name_part.strip().replace('*', '').replace('(Corresponding Author)', '')
                            # Handle multiple names like (A; B, email)
                            name = name.split(';')[-1].strip() 
                            
                            if email_clean not in corresponding_info:
                                corresponding_info[email_clean] = name
                            emails_found_in_record.add(email_clean)

                # 2. Find *any* other emails in the *entire record* as a fallback
                # This ensures we still capture emails even if the (Name, email) format isn't matched
                all_emails_in_record = set(email.lower() for email in EMAIL_RE.findall(full_record_text))
                for email in all_emails_in_record:
                    emails_found_in_record.add(email) # Add to the master list
                    if email not in corresponding_info:
                        # Email found, but no name paired.
                        # Use first_author if available, else 'N/A'
                        corresponding_info[email] = first_author if first_author else "N/A"

                # Add entries for this record if we found a title and at least one email
                if title and emails_found_in_record:
                    authors_str = '; '.join(all_authors)
                    keywords_str = '; '.join(keywords)
                    
                    # Use the master set of all emails found
                    for email in emails_found_in_record:
                        # Get the name we stored (either from pair or fallback)
                        name = corresponding_info.get(email, first_author if first_author else "N/A")
                        
                        st.session_state['all_parsed_data'].append({
                            'Title': title,
                            'Year': year,
                            'Journal': journal,
                            'Corresponding Author': name,
                            'Email': email,
                            'All Authors': authors_str,
                            'Keywords': keywords_str,
                            'Source File': uploaded.name
                        })

        # === Handle results ===
        if not st.session_state['all_parsed_data']:
            st.error("❌ No records with corresponding emails were found in any of the files.")
            st.stop()

        # Create DataFrame and remove duplicates
        df = pd.DataFrame(st.session_state['all_parsed_data'])
        df = df.drop_duplicates(subset=['Title', 'Email']).reset_index(drop=True)
        
        st.success(f"✅ Extracted {len(df)} unique Title/Email combinations from {len(uploaded_files)} file(s)!")
        
        # Reorder columns to be more logical
        columns_order = [
            'Title', 'Year', 'Journal', 'Corresponding Author', 'Email', 
            'All Authors', 'Keywords', 'Source File'
        ]
        # Ensure all columns exist before trying to reorder
        final_columns = [col for col in columns_order if col in df.columns]
        st.dataframe(df[final_columns], use_container_width=True)

        # === Download buttons ===
        csv_bytes = df[final_columns].to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download as CSV",
            data=csv_bytes,
            file_name="ris_extracted_data.csv",
            mime="text/csv",
            key="csv_download"
        )

        buf = BytesIO()
        df[final_columns].to_excel(buf, index=False, engine="openpyxl")
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

elif 'all_parsed_data' in st.session_state and st.session_state['all_parsed_data']:
    # Show a clear button if there are old results
    st.info("Results from previous upload are shown below.")
    st.button("Clear Old Results", on_click=clear_results)
    
    # (Display old results - code copied from above for simplicity)
    df = pd.DataFrame(st.session_state['all_parsed_data'])
    df = df.drop_duplicates(subset=['Title', 'Email']).reset_index(drop=True)
    st.success(f"✅ Displaying {len(df)} unique combinations from previous run.")
    columns_order = [
        'Title', 'Year', 'Journal', 'Corresponding Author', 'Email', 
        'All Authors', 'Keywords', 'Source File'
    ]
    final_columns = [col for col in columns_order if col in df.columns]
    st.dataframe(df[final_columns], use_container_width=True)
    csv_bytes = df[final_columns].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download as CSV", data=csv_bytes, file_name="ris_extracted_data.csv", mime="text/csv", key="csv_download_old")
    buf = BytesIO()
    df[final_columns].to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    st.download_button("⬇️ Download as Excel", data=buf, file_name="ris_extracted_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="excel_download_old")

else:
    st.info("👆 Upload your .ris file(s) to begin.")
