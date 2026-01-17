import os
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
import io

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service():
    """Get Google Drive service using service account credentials"""
    try:
        creds_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
        if creds_file and os.path.exists(creds_file):
            credentials = service_account.Credentials.from_service_account_file(
                creds_file, scopes=SCOPES
            )
            return build('drive', 'v3', credentials=credentials)
        
        # Try JSON credentials from environment
        import json
        creds_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
        if creds_json:
            creds_info = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_info, scopes=SCOPES
            )
            return build('drive', 'v3', credentials=credentials)
        
        logger.warning("No Google Drive credentials configured")
        return None
        
    except Exception as e:
        logger.error(f"Error creating Drive service: {e}")
        return None

def get_teacher_drive_manager(teacher):
    """Get a drive manager configured for a specific teacher's folder"""
    service = get_drive_service()
    if not service:
        return None
    
    folder_id = teacher.get('google_drive_folder_id') if teacher else None
    return DriveManager(service, folder_id)

class DriveManager:
    def __init__(self, service, folder_id=None):
        self.service = service
        self.folder_id = folder_id
    
    def create_folder(self, name: str, parent_id: str = None) -> str:
        """Create a folder in Drive"""
        try:
            file_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id or self.folder_id:
                file_metadata['parents'] = [parent_id or self.folder_id]
            
            file = self.service.files().create(
                body=file_metadata, 
                fields='id'
            ).execute()
            
            return file.get('id')
        except Exception as e:
            logger.error(f"Error creating folder: {e}")
            return None
    
    def upload_file(self, file_path: str, name: str = None, folder_id: str = None) -> dict:
        """Upload a file to Drive"""
        try:
            if not name:
                name = os.path.basename(file_path)
            
            file_metadata = {'name': name}
            if folder_id or self.folder_id:
                file_metadata['parents'] = [folder_id or self.folder_id]
            
            # Determine mime type
            mime_type = 'application/octet-stream'
            if file_path.endswith('.pdf'):
                mime_type = 'application/pdf'
            elif file_path.endswith('.txt'):
                mime_type = 'text/plain'
            elif file_path.endswith('.json'):
                mime_type = 'application/json'
            
            media = MediaFileUpload(file_path, mimetype=mime_type)
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()
            
            return {
                'id': file.get('id'),
                'link': file.get('webViewLink')
            }
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return None
    
    def upload_content(self, content: bytes, name: str, mime_type: str = 'application/pdf', folder_id: str = None) -> dict:
        """Upload content directly to Drive"""
        try:
            file_metadata = {'name': name}
            if folder_id or self.folder_id:
                file_metadata['parents'] = [folder_id or self.folder_id]
            
            media = MediaIoBaseUpload(
                io.BytesIO(content),
                mimetype=mime_type,
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()
            
            return {
                'id': file.get('id'),
                'link': file.get('webViewLink')
            }
        except Exception as e:
            logger.error(f"Error uploading content: {e}")
            return None
    
    def delete_file(self, file_id: str) -> bool:
        """Delete a file from Drive"""
        try:
            self.service.files().delete(fileId=file_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return False

def upload_assignment_file(file_path: str, assignment: dict, teacher: dict) -> dict:
    """
    Upload an assignment-related file to the teacher's Drive folder
    """
    manager = get_teacher_drive_manager(teacher)
    if not manager:
        logger.warning("Drive manager not available")
        return None
    
    # Create assignment folder if it doesn't exist
    folder_name = f"Assignment_{assignment.get('assignment_id', 'Unknown')}"
    folder_id = manager.create_folder(folder_name)
    
    if folder_id:
        return manager.upload_file(file_path, folder_id=folder_id)
    
    return manager.upload_file(file_path)
