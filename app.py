import streamlit as st
import pandas as pd
from crawler import run_crawler

st.set_page_config(page_title="Powerful Author Email Extractor", layout="wide")
st.title("🔥 ULTRA POWERFUL Author Email Extractor")
st.markdown("### Deep Crawl | PDF Extraction | Corresponding Author Detection")

# Sidebar info
with st.sidebar:
    st.header("⚙️ How It Works")
    st.markdown("""
    1. **Deep Crawl** - Crawls up to 100 pages
    2. **PDF Scanner** - Opens and reads all PDFs
    3. **Corresponding Author Detection** - Finds main authors
    4. **Name & Affiliation Extraction** - Gets full author details
    
    **🚀 Features:**
    - ✅ Deep crawling up to 3 levels
    - ✅ Automatic PDF download & read
    - ✅ Corresponding author detection
    - ✅ Name & affiliation extraction
    - ✅ Garbage email filtering
    - ✅ Up to 100 pages per site
    """)
    
    st.header("🎯 Best URLs")
    st.code("""
    # Journal Editorial Pages
    https://mdpi.com/journal/sensors/editors
    
    # Conference Proceedings
    https://icml.cc/2025/accepted-papers
    
    # University Departments
    https://cs.stanford.edu/people
    
    # Open Access Journals
    https://www.frontiersin.org/journals
    """)

# Main input
st.header("📌 Input")
col1, col2 = st.columns([3, 1])
with col1:
    url = st.text_input(
        "Journal/Conference/University URL", 
        placeholder="https://mdpi.com/journal/sensors/editors",
        help="Enter any research-related website URL"
    )
with col2:
    depth = st.selectbox(
        "Crawling Depth", 
        [2, 3], 
        index=0,
        help="Depth 2 = 2 levels, Depth 3 = 3 levels (more thorough)"
    )

st.info("💡 **Tip:** Use Depth 3 for best results. The crawler will scan up to 100 pages and all PDFs automatically.")

# Start button
if st.button("🚀 START POWERFUL EXTRACTION", type="primary", use_container_width=True):
    if url:
        status_placeholder = st.empty()
        status_placeholder.info("🔍 Starting deep crawl... This will take 2-5 minutes depending on site size")
        
        with st.spinner("🕷️ Deep crawling website, scanning PDFs, and extracting author emails..."):
            results = run_crawler(url, depth)
        
        if results:
            df = pd.DataFrame(results, columns=["Email", "Author Name", "Affiliation", "Type", "Source URL"])
            df = df.drop_duplicates(subset=["Email"])
            
            # Statistics
            st.success(f"✅ Successfully extracted {len(df)} author emails!")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Authors", len(df))
            with col2:
                corresponding = len(df[df["Type"] == "Corresponding Author"])
                st.metric("Corresponding Authors", corresponding)
            with col3:
                with_name = len(df[df["Author Name"] != "Unknown"])
                st.metric("With Names Found", with_name)
            with col4:
                with_aff = len(df[df["Affiliation"] != "Unknown"])
                st.metric("With Affiliations", with_aff)
            
            # Display results
            st.subheader("📧 Extracted Author Emails")
            st.dataframe(df[["Email", "Author Name", "Affiliation", "Type"]], use_container_width=True, height=400)
            
            # Download buttons
            col1, col2 = st.columns(2)
            with col1:
                csv_full = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Download Full CSV",
                    csv_full,
                    "all_author_emails.csv",
                    "text/csv",
                    use_container_width=True
                )
            with col2:
                # Corresponding authors only
                corresponding_df = df[df["Type"] == "Corresponding Author"]
                if len(corresponding_df) > 0:
                    csv_corr = corresponding_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "⭐ Download Corresponding Authors Only",
                        csv_corr,
                        "corresponding_authors.csv",
                        "text/csv",
                        use_container_width=True
                    )
            
            # Show sample emails
            with st.expander("🔍 View All Emails"):
                st.write(df[["Email", "Author Name", "Affiliation"]].to_string())
        else:
            st.warning("⚠️ No emails found. Try a different URL or increase depth to 3.")
    else:
        st.error("❌ Please enter a URL")