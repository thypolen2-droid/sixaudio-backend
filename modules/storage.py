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
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

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

def get_storage_provider() -> StorageProvider:
    bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET")
    if bucket_name:
        return CloudStorageProvider(bucket_name)
    else:
        return LocalStorageProvider(os.environ.get("LIBRARY_PATH", "Library"))
