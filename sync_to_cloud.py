import os
import sys
import argparse
from pathlib import Path

def get_or_create_folder(service, folder_name: str, parent_id: str) -> str:
    query = f"'{parent_id}' in parents and name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    else:
        file_metadata = {
            'name': folder_name,
            'parents': [parent_id],
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

def sync_folder(local_path, drive_folder_id):
    """
    Syncs a local folder to Google Drive.
    """
    # Auto-install dependencies
    for package in ['google-api-python-client', 'google-auth-httplib2', 'google-auth-oauthlib', 'tqdm']:
        try:
            if package == 'google-api-python-client':
                import googleapiclient
            elif package == 'google-auth-httplib2':
                import google_auth_httplib2
            elif package == 'google-auth-oauthlib':
                import google_auth_oauthlib
            else:
                import tqdm
        except ImportError:
            print(f"📦 Missing dependency: {package}. Installing...")
            os.system(f"{sys.executable} -m pip install {package}")

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from tqdm import tqdm
    except Exception as e:
        print(f"❌ Failed to load packages: {e}")
        return

    try:
        key_file = "firebase-key.json"
        if not os.path.exists(key_file):
            print("❌ No 'firebase-key.json' found! Google Drive requires this.")
            return

        print(f"🔑 Authenticating with {key_file}...")
        SCOPES = ['https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        
        # Verify folder existence
        service.files().get(fileId=drive_folder_id, fields="id, name").execute()
    except Exception as e:
        print(f"❌ Error connecting to Google Drive: {e}")
        print("💡 Hint: Ensure you shared the folder with the service account as Editor.")
        return

    local_path = Path(local_path)
    if not local_path.exists():
        print(f"❌ Local path {local_path} does not exist.")
        return

    print(f"🚀 Starting sync to Google Drive (Folder ID: {drive_folder_id})")

    # Get all files recursively
    files_to_upload = [f for f in local_path.rglob("*") if f.is_file() and not f.name.startswith(".")]

    if not files_to_upload:
        print("⚠️ No files found to upload in 'Library' folder.")
        return

    pbar = tqdm(total=len(files_to_upload), desc="Uploading")

    folder_cache = {}

    for local_file in files_to_upload:
        relative_path = local_file.relative_to(local_path)
        
        current_parent_id = drive_folder_id
        # Create/Get necessary folders in Drive
        for part in relative_path.parent.parts:
            cache_key = f"{current_parent_id}/{part}"
            if cache_key not in folder_cache:
                folder_cache[cache_key] = get_or_create_folder(service, part, current_parent_id)
            current_parent_id = folder_cache[cache_key]
        
        # Check if file exists
        query = f"'{current_parent_id}' in parents and name='{local_file.name}' and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields="files(id, name, size)").execute()
        existing_files = results.get('files', [])
        
        if existing_files:
            # We skip if size matches roughly (Drive API size is string)
            # Due to precision we just skip if exists for simplicity, or we can check exact size
            pbar.update(1)
            continue
        
        # Upload
        content_type = "audio/mpeg" if local_file.suffix == ".mp3" else "text/plain"
        if local_file.suffix == ".json": content_type = "application/json"
        
        file_metadata = {
            'name': local_file.name,
            'parents': [current_parent_id]
        }
        media = MediaFileUpload(str(local_file), mimetype=content_type, resumable=True)
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        
        pbar.update(1)

    pbar.close()
    print(f"\n✅ Sync complete!")
    print(f"📖 Files are now available in your Google Drive.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync local Library to Google Drive")
    parser.add_argument("--folder-id", default="1H2QPt_u3e0RK-aNN57Bhqywwch5qskf6", help="Google Drive Folder ID to upload into")
    parser.add_argument("--local", default="Library", help="Local folder to sync (default: Library)")
    
    args = parser.parse_args()
    sync_folder(args.local, args.folder_id)
