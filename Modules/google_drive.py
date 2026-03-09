import os
import pickle
import io
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# 權限範圍：讀寫 Drive
SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveClient:
    def __init__(self, credentials_path='credentials.json'):
        self.creds = None
        self.service = None
        self.credentials_path = credentials_path
        self.token_path = 'token.pickle'
        self.authenticate()

    def authenticate(self):
        """處理 OAuth2 登入與 Token 管理"""
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                self.creds = pickle.load(token)
        
        # 如果沒有憑證或憑證過期
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception:
                    # Refresh 失敗 (例如 token 被撤銷)，重新登入
                    os.remove(self.token_path)
                    self.creds = None
            
            if not self.creds:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(f"[Error] 找不到 {self.credentials_path}！請先至 Google Cloud Console 下載 OAuth 憑證。")
                
                print("[GoogleDrive] 需要進行瀏覽器登入授權...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES)
                self.creds = flow.run_local_server(port=0)
            
            # 儲存 token 下次不用登入
            with open(self.token_path, 'wb') as token:
                pickle.dump(self.creds, token)

        self.service = build('drive', 'v3', credentials=self.creds)
        print("[GoogleDrive] 登入成功！服務已連線。")

    def upload_file(self, file_path, folder_id=None):
        """上傳檔案並回傳 File ID"""
        if not os.path.exists(file_path):
            print(f"[Error] 找不到要上傳的檔案: {file_path}")
            return None

        name = os.path.basename(file_path)
        file_metadata = {'name': name}
        if folder_id:
            file_metadata['parents'] = [folder_id]

        media = MediaFileUpload(file_path, resumable=True)
        
        print(f"[GoogleDrive] 正在上傳 {name} ...")
        try:
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            file_id = file.get('id')
            print(f"[GoogleDrive] 上傳完成。File ID: {file_id}")
            
            # 設定權限：讓擁有 ID 的人可以讀取 (Reader)
            # 這是為了讓接收端不用登入發送者的帳號也能下載
            self.service.permissions().create(
                fileId=file_id,
                body={'role': 'reader', 'type': 'anyone'},
                fields='id',
            ).execute()
            
            return file_id
        except Exception as e:
            print(f"[GoogleDrive] 上傳失敗: {e}")
            return None

    def download_file(self, file_id, save_path):
        """根據 File ID 下載檔案"""
        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            print(f"[GoogleDrive] 正在下載 ID: {file_id} ...")
            while done is False:
                status, done = downloader.next_chunk()
                # print(f"Download {int(status.progress() * 100)}%.")

            with open(save_path, 'wb') as f:
                f.write(fh.getbuffer())
            
            print(f"[GoogleDrive] 下載成功 -> {save_path}")
            return True
            
        except Exception as e:
            print(f"[GoogleDrive] 下載失敗 (可能 ID 錯誤或無權限): {e}")
            return False