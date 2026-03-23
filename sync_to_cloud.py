import os
import sys
import argparse
from pathlib import Path
from google.cloud import storage
from tqdm import tqdm

def sync_folder(local_path, bucket_name, project_id):
    """
    Syncs a local folder to a GCS bucket.
    """
    try:
        client = storage.Client(project=project_id)
        bucket = client.bucket(bucket_name)
    except Exception as e:
        print(f"❌ Error initializing GCS client: {e}")
        print("💡 Tip: Make sure you've run 'gcloud auth application-default login'")
        return

    local_path = Path(local_path)
    if not local_path.exists():
        print(f"❌ Local path {local_path} does not exist.")
        return

    print(f"🚀 Starting sync: {local_path} -> gs://{bucket_name}/")

    # Get all files recursively
    files_to_upload = [f for f in local_path.rglob("*") if f.is_file()]
    
    # Filter out hidden files or unwanted types
    files_to_upload = [f for f in files_to_upload if not f.name.startswith(".")]

    pbar = tqdm(total=len(files_to_upload), desc="Uploading")

    for local_file in files_to_upload:
        # Construct relative path for GCS
        relative_path = local_file.relative_to(local_path)
        gcs_path = str(relative_path).replace("\\", "/") # Ensure forward slashes for GCS
        
        blob = bucket.blob(gcs_path)
        
        # Check if file exists and has same size to avoid redundant uploads
        if blob.exists():
            if blob.size == local_file.stat().st_size:
                pbar.update(1)
                continue
        
        # Determine content type
        content_type = "audio/mpeg" if local_file.suffix == ".mp3" else "text/plain"
        if local_file.suffix == ".json": content_type = "application/json"
        
        blob.upload_from_filename(str(local_file), content_type=content_type)
        pbar.update(1)

    pbar.close()
    print(f"✅ Sync complete! Your stories are now live at your Firebase URL.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync local Library to Firebase Storage")
    parser.add_argument("--bucket", required=True, help="Firebase Storage bucket name (e.g. project-id.appspot.com)")
    parser.add_argument("--project", required=True, help="Google Cloud Project ID")
    parser.add_argument("--folder", default="Library", help="Local folder to sync (default: Library)")
    
    args = parser.parse_args()
    
    # Check if tqdm is installed, if not, install it or use simple print
    try:
        import tqdm
    except ImportError:
        print("Installing tqdm for progress bars...")
        os.system("pip install tqdm")
        
    sync_folder(args.folder, args.bucket, args.project)
