import os
from pathlib import Path
from typing import List, Dict, Optional
from google.cloud import storage
import datetime

class StorageProvider:
    def list_stories(self) -> List[str]:
        raise NotImplementedError
    
    def list_chapters(self, story_name: str) -> List[str]:
        raise NotImplementedError
    
    def get_audio_url(self, story_name: str, filename: str) -> str:
        raise NotImplementedError

class LocalStorageProvider(StorageProvider):
    def __init__(self, library_path: str):
        self.library_path = Path(library_path)

    def list_stories(self) -> List[str]:
        if not self.library_path.exists(): return []
        return sorted([d.name for d in self.library_path.iterdir() if d.is_dir()])

    def list_chapters(self, story_name: str) -> List[str]:
        audio_dir = self.library_path / story_name / "Audios"
        if not audio_dir.exists(): return []
        return sorted([f.name for f in audio_dir.glob("*.mp3") if not f.name.startswith("combined_")])

    def get_audio_url(self, story_name: str, filename: str) -> str:
        # Locally, this is handled by a FileResponse in FastAPI
        return f"/stream/{story_name}/{filename}"

class CloudStorageProvider(StorageProvider):
    def __init__(self, bucket_name: str):
        try:
            print(f"📡 Connecting to Firebase Storage bucket: {bucket_name}")
            self.client = storage.Client()
            self.bucket = self.client.bucket(bucket_name.replace('gs://', ''))
            print(f"✅ Bucket connection initialized: {self.bucket.name}")
        except Exception as e:
            print(f"❌ Failed to initialize CloudStorageProvider: {str(e)}")
            raise

    def list_stories(self) -> List[str]:
        # Stories are represented as folders at the top level
        blobs = self.client.list_blobs(self.bucket, prefix="", delimiter="/")
        # Extract folder names from the iterator.prefixes
        _ = list(blobs) # Consume iterator
        prefixes = [p.strip("/") for p in blobs.prefixes]
        return sorted(prefixes)

    def list_chapters(self, story_name: str) -> List[str]:
        prefix = f"{story_name}/Audios/"
        blobs = self.client.list_blobs(self.bucket, prefix=prefix)
        files = []
        for b in blobs:
            name = b.name.replace(prefix, "")
            if name.endswith(".mp3") and not name.startswith("combined_"):
                files.append(name)
        return sorted(files)

    def get_audio_url(self, story_name: str, filename: str) -> str:
        # Generate a signed URL for secure streaming
        blob = self.bucket.blob(f"{story_name}/Audios/{filename}")
        return blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(hours=1),
            method="GET"
        )

from google.oauth2 import service_account
from googleapiclient.discovery import build
import functools

class GoogleDriveStorageProvider(StorageProvider):
    def __init__(self, folder_id: str):
        self.folder_id = folder_id
        try:
            print(f"📡 Connecting to Google Drive (Folder ID: {folder_id})")
            SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
            creds = service_account.Credentials.from_service_account_file('firebase-key.json', scopes=SCOPES)
            self.service = build('drive', 'v3', credentials=creds, cache_discovery=False)
            print(f"✅ Google Drive connection initialized.")
        except Exception as e:
            print(f"❌ Failed to initialize GoogleDriveStorageProvider: {str(e)}")
            raise

    def list_stories(self) -> List[str]:
        # Stories are folders inside the main folder
        query = f"'{self.folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
        return sorted([f['name'] for f in results.get('files', [])])

    @functools.lru_cache(maxsize=128)
    def _get_story_folder_id(self, story_name: str) -> Optional[str]:
        query = f"'{self.folder_id}' in parents and name='{story_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
        files = results.get('files', [])
        return files[0]['id'] if files else None

    def list_chapters(self, story_name: str) -> List[str]:
        story_id = self._get_story_folder_id(story_name)
        if not story_id:
            return []
            
        # Audio directory inside story
        query = f"'{story_id}' in parents and name='Audios' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
        audio_folders = results.get('files', [])
        
        if not audio_folders:
            return []
            
        audio_folder_id = audio_folders[0]['id']
        
        # Audio files
        query = f"'{audio_folder_id}' in parents and mimeType contains 'audio/' and trashed=false"
        # We might have many files, so we iterate
        files = []
        page_token = None
        while True:
            results = self.service.files().list(q=query, spaces='drive', fields="nextPageToken, files(id, name)", pageToken=page_token).execute()
            for f in results.get('files', []):
                if not f['name'].startswith("combined_") and f['name'].endswith(".mp3"):
                    files.append(f['name'])
            page_token = results.get('nextPageToken')
            if not page_token:
                break
                
        return sorted(files)

    @functools.lru_cache(maxsize=256)
    def _get_file_id(self, story_name: str, filename: str) -> Optional[str]:
        story_id = self._get_story_folder_id(story_name)
        if not story_id: return None
        
        query = f"'{story_id}' in parents and name='Audios' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
        audio_folders = results.get('files', [])
        if not audio_folders: return None
        
        audio_folder_id = audio_folders[0]['id']
        
        query = f"'{audio_folder_id}' in parents and name='{filename}' and trashed=false"
        results = self.service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
        files = results.get('files', [])
        return files[0]['id'] if files else None

    def get_audio_url(self, story_name: str, filename: str) -> str:
        file_id = self._get_file_id(story_name, filename)
        if not file_id:
            # Fallback local URL if not found visually
            return f"/stream/{story_name}/{filename}"
        
        # This streams the file directly from Google Drive.
        # Note: The folder MUST be shared as "Anyone with the link" = "Viewer"
        return f"https://drive.google.com/uc?export=download&id={file_id}"

def get_storage_provider() -> StorageProvider:
    # Use the Google Drive Folder ID provided by the user
    drive_folder_id = os.environ.get("DRIVE_FOLDER_ID", "1H2QPt_u3e0RK-aNN57Bhqywwch5qskf6")
    if drive_folder_id:
        return GoogleDriveStorageProvider(drive_folder_id)
        
    bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET")
    if bucket_name:
        return CloudStorageProvider(bucket_name)
    else:
        return LocalStorageProvider(os.environ.get("LIBRARY_PATH", "Library"))
