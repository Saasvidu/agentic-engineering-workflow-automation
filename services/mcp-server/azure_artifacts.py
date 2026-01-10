"""
Azure Blob Storage artifact URL generation for MCP server.

Provides secure, time-limited SAS URLs for job artifacts stored in Azure Blob Storage.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from azure.storage.blob import BlobServiceClient, generate_container_sas, BlobSasPermissions
from azure.core.exceptions import AzureError

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "fea-job-data")
ARTIFACT_SAS_TTL_SECONDS = int(os.getenv("ARTIFACT_SAS_TTL_SECONDS", "3600"))


# ============================================================================
# Response Model
# ============================================================================

from pydantic import BaseModel


class ArtifactUrlsResponse(BaseModel):
    """Response model for artifact URLs endpoint."""
    job_id: str
    expires_in_seconds: int
    base_path: str
    artifacts: Dict[str, Optional[str]]  # Keys: summary, preview_png, mesh_glb, mesh_vtu


# ============================================================================
# Helper Functions
# ============================================================================

def build_artifact_urls(job_id: str, ttl_seconds: int = None) -> Dict[str, Optional[str]]:
    """
    Generate time-limited, read-only SAS URLs for job artifacts.
    
    Args:
        job_id: Unique job identifier
        ttl_seconds: Time-to-live for SAS token in seconds (defaults to env var or 3600)
        
    Returns:
        Dictionary with artifact URLs:
        - summary: URL for summary.json
        - preview_png: URL for preview.png
        - mesh_glb: URL for mesh.glb
        - mesh_vtu: URL for mesh.vtu
        
    Raises:
        ValueError: If Azure connection string is not configured
        AzureError: If Azure SDK operations fail
    """
    if not AZURE_CONNECTION_STRING:
        raise ValueError(
            "AZURE_STORAGE_CONNECTION_STRING environment variable is not set. "
            "Cannot generate artifact URLs."
        )
    
    if ttl_seconds is None:
        ttl_seconds = ARTIFACT_SAS_TTL_SECONDS
    
    try:
        # Create BlobServiceClient from connection string
        service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        account_name = service_client.account_name
        
        # Parse connection string to extract account key
        # Connection string format: "DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=..."
        account_key = None
        for part in AZURE_CONNECTION_STRING.split(';'):
            if part.startswith('AccountKey='):
                account_key = part.split('=', 1)[1]
                break
        
        if not account_key:
            raise ValueError("AccountKey not found in connection string")
        
        # Generate container-level SAS token with read-only permissions
        expiry_time = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        
        sas_token = generate_container_sas(
            account_name=account_name,
            container_name=AZURE_STORAGE_CONTAINER_NAME,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time,
            protocol="https"  # HTTPS-only for security
        )
        
        # Build base URL
        base_url = f"https://{account_name}.blob.core.windows.net/{AZURE_STORAGE_CONTAINER_NAME}"
        
        # Define artifact paths
        artifact_paths = {
            "summary": f"{job_id}/summary.json",
            "preview_png": f"{job_id}/data/preview.png",
            "mesh_glb": f"{job_id}/data/mesh.glb",
            "mesh_vtu": f"{job_id}/data/mesh.vtu",
        }
        
        # Build signed URLs for each artifact
        artifact_urls = {}
        for key, blob_path in artifact_paths.items():
            # Construct full URL with SAS token
            artifact_url = f"{base_url}/{blob_path}?{sas_token}"
            artifact_urls[key] = artifact_url
        
        logger.info(f"Generated artifact URLs for job {job_id} (expires in {ttl_seconds}s)")
        
        return artifact_urls
        
    except AzureError as e:
        logger.error(f"Azure SDK error while generating artifact URLs for job {job_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while generating artifact URLs for job {job_id}: {e}")
        raise


def check_blob_exists(blob_client, blob_path: str) -> bool:
    """
    Check if a blob exists in Azure Storage.
    
    Args:
        blob_client: BlobClient instance
        blob_path: Path to the blob
        
    Returns:
        True if blob exists, False otherwise
    """
    try:
        blob_client.get_blob_properties()
        return True
    except AzureError:
        return False
