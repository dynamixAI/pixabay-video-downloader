import streamlit as st
import requests
import os
import io
import zipfile
# Removed from google.colab import userdata as it's not needed on Streamlit Cloud

# Removed tqdm.notebook, use standard tqdm as it's a regular Python env on Streamlit Cloud
from tqdm import tqdm

# --- 0. Streamlit GUI Setup & Initialization ---
st.set_page_config(
    page_title="Pixabay Video Downloader",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state variables
if 'downloaded_files' not in st.session_state:
    st.session_state.downloaded_files = []
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# --- Authentication Layer ---
# Retrieve the valid user key from Streamlit Cloud secrets
# You MUST set 'VALID_USER_KEY' as a secret in Streamlit Cloud (next step)
VALID_USER_KEY = st.secrets["uchennA4326"] # This will be set in Streamlit Cloud

if not st.session_state.authenticated:
    st.sidebar.title("App Access")
    user_key_input = st.sidebar.text_input(
        "Enter your access key",
        type="password",
        help="This is the alpha-numeric key provided by the app owner."
    )
    if st.sidebar.button("Login"):
        if user_key_input == VALID_USER_KEY:
            st.session_state.authenticated = True
            st.sidebar.success("Logged in successfully!")
            st.rerun() # Rerun to hide login and show main app
        else:
            st.sidebar.error("Invalid access key. Please try again.")
    st.stop() # Stop execution if not authenticated


# --- If authenticated, proceed with the main app ---
st.title("🎬 Pixabay Video Downloader")
st.write("Enter your preferences to search and download royalty-free videos from Pixabay.")

# --- API Key Retrieval from Streamlit Cloud Secrets ---
# This key is stored securely on Streamlit Cloud and is NOT exposed to the user.
try:
    current_api_key = st.secrets["24264058-740cd5f093abc58aab8f8ddb4"]
    st.sidebar.success("Pixabay API Key loaded!")
except KeyError:
    st.sidebar.error("Pixabay API Key not found in Streamlit secrets. Please configure it.")
    st.stop() # Stop if API key is not configured


# --- 1. User Input Collection via Streamlit GUI (Main App UI) ---
search_keyword = st.text_input("Search Keyword(s)", "nature", help="e.g., 'cityscape', 'ocean', 'work'")

col1, col2 = st.columns(2)
min_duration = col1.number_input("Min Duration (seconds)", min_value=1, value=10, help="Minimum duration for videos in seconds.")
max_duration = col2.number_input("Max Duration (seconds)", min_value=1, value=30, help="Maximum duration for videos in seconds.")

video_quality = st.selectbox(
    "Preferred Video Quality",
    ["medium", "small", "tiny", "large"],
    index=0, # 'medium' as default
    help="Choose the resolution of the videos to download. 'large' is highest."
)
num_videos_to_download = st.slider("Number of Videos to Download", min_value=1, max_value=20, value=5, help="How many videos to download.")

download_button_clicked = st.button("Search & Download Videos 🚀")

# Placeholder for messages and progress bar in the main area
status_message = st.empty()
progress_bar = st.progress(0)


# --- 2. Execution Logic (Triggered by Button) ---
if download_button_clicked:
    # --- Input Validation ---
    if min_duration >= max_duration:
        status_message.error("Minimum duration must be less than maximum duration.")
        st.stop()

    # Reset State for new download attempt
    st.session_state.downloaded_files = []
    progress_bar.progress(0) # Reset progress bar
    status_message.info("Starting video search and download process...")

    # --- Phase 2: Fetch Videos from Pixabay API ---
    PIXABAY_API_URL = "https://pixabay.com/api/videos/"
    params = {
        "key": current_api_key, # Use the securely loaded API key
        "q": search_keyword,
        "per_page": 200, # Max per page
        "page": 1, # Start with the first page
    }

    eligible_videos = []
    videos_fetched_count = 0
    total_pages_to_check = 2 # Check up to 2 pages to find enough videos, adjust as needed

    with st.spinner("Searching Pixabay for videos..."):
        for page in range(1, total_pages_to_check + 1): # You can increase total_pages_to_check
            params["page"] = page
            try:
                response = requests.get(PIXABAY_API_URL, params=params)
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                data = response.json()

                videos_fetched_count += len(data.get("hits", []))

                if not data.get("hits"):
                    break # No more videos on this page

                # --- Phase 3: Filter and Select Videos ---
                for video in data["hits"]:
                    duration = video.get("duration")
                    if duration is not None and min_duration <= duration <= max_duration:
                        # Check if the desired quality URL exists
                        if video["videos"].get(video_quality):
                            eligible_videos.append(video)
                            if len(eligible_videos) >= num_videos_to_download:
                                break # Stop once we have enough videos

            except requests.exceptions.RequestException as e:
                status_message.error(f"Error fetching from Pixabay API: {e}. Check your API key or network.")
                st.stop()
            except Exception as e:
                status_message.error(f"An unexpected error occurred during search: {e}")
                st.stop()

            if len(eligible_videos) >= num_videos_to_download:
                break # Break outer loop if enough videos found


    if not eligible_videos:
        status_message.warning("No videos found matching your criteria.")
        st.stop()

    status_message.info(f"Found {len(eligible_videos)} videos matching criteria. Starting download...")

    # --- Phase 4: Download Selected Videos ---
    # Create a temporary directory or use in-memory for download button
    # Streamlit Cloud's filesystem is ephemeral, so in-memory is best for downloads to user
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for i, video in enumerate(eligible_videos):
            if len(st.session_state.downloaded_files) >= num_videos_to_download:
                break # Ensure we don't download more than requested

            download_url = video["videos"][video_quality]["url"]
            video_id = video.get("id", f"unknown_id_{i}")
            # Use a simple .mp4 extension, most Pixabay videos are mp4
            filename = f"pixabay_video_{video_id}.mp4"

            try:
                video_response = requests.get(download_url, stream=True)
                video_response.raise_for_status() # Check for bad responses

                # Download with progress bar
                total_size = int(video_response.headers.get('content-length', 0))
                bytes_downloaded = 0
                video_content_buffer = io.BytesIO()

                for chunk in tqdm(video_response.iter_content(chunk_size=8192),
                                 total=total_size // 8192, unit='KB',
                                 desc=f"Downloading {filename}"):
                    video_content_buffer.write(chunk)
                    bytes_downloaded += len(chunk)
                    progress = int(bytes_downloaded / total_size * 100) if total_size else 0
                    progress_bar.progress(progress)
                    status_message.text(f"Downloading {i+1}/{len(eligible_videos)}: {filename} ({progress}%)")

                # Add video to zip file
                zip_file.writestr(filename, video_content_buffer.getvalue())
                st.session_state.downloaded_files.append(filename) # Keep track of names

            except requests.exceptions.RequestException as e:
                status_message.error(f"Error downloading {filename}: {e}")
                continue # Try next video
            except Exception as e:
                status_message.error(f"An unexpected error occurred during download of {filename}: {e}")
                continue

    progress_bar.progress(100) # Ensure progress bar is full
    status_message.success(f"Successfully downloaded {len(st.session_state.downloaded_files)} videos!")

    # --- Phase 5: Final Summary & Download Button ---
    if st.session_state.downloaded_files:
        zip_buffer.seek(0) # Rewind buffer to the beginning
        st.download_button(
            label="Download All Videos as ZIP",
            data=zip_buffer.getvalue(),
            file_name="pixabay_videos.zip",
            mime="application/zip",
            help="Click to download all selected videos in a single ZIP file."
        )
        st.write("---")
        st.write("You can also view individual video details below:")
        for filename in st.session_state.downloaded_files:
            st.write(f"- {filename}") # Just list names, actual content not persistent for display
    else:
        status_message.warning("No videos were successfully downloaded.")
