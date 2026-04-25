# backend/utils/gcs_utils.py

import os
from pathlib import Path
from google.cloud import storage

def upload_to_gcs(local_file_path: Path, destination_blob_name: str) -> str | None:
    """
    Uploads a file to a Google Cloud Storage bucket and returns its public URL.

    Args:
        local_file_path: The path to the file on your local machine.
        destination_blob_name: The desired path and filename in the GCS bucket
                               (e.g., "projects/project_id/presentation.pptx").

    Returns:
        The public URL of the uploaded file, or None if the upload fails.
    """
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        print("GCS_BUCKET_NAME environment variable not set. Skipping upload.")
        return None

    try:
        project_id = os.getenv("GCP_PROJECT_ID")
        if not project_id:
            print("Warning: GCP_PROJECT_ID environment variable is not set. The GCS client may fail.")

        # Initialize the GCS client, explicitly passing the project ID.
        storage_client = storage.Client(project=project_id)

        # Get the target bucket from the client.
        bucket = storage_client.bucket(bucket_name)

        # Create a new "blob" (the object that will be stored in the bucket).
        blob = bucket.blob(destination_blob_name)

        print(f"Uploading {local_file_path.name} to GCS bucket '{bucket_name}'...")

        # Set content type and disposition
        content_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        
        # Upload the local file to the new blob.
        blob.upload_from_filename(str(local_file_path), content_type=content_type)
        
        # Set the content disposition to "inline"
        blob.content_disposition = 'inline'
        blob.patch()

        print(f"File successfully uploaded. Public URL: {blob.public_url}")

        # Return the public URL.
        return blob.public_url

    except Exception as e:
        print(f"Error uploading to Google Cloud Storage: {e}")
        return None