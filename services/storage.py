import os
import requests
from typing import Union
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET_NAME = os.getenv("SUPABASE_BUCKET_NAME", "userdoc-media")

LOCAL_STATIC_DIR = "static"

def upload_file_to_storage(
    file_data: Union[bytes, any],
    file_name: str,
    content_type: str = "image/png",
    folder: str = "avatars",
) -> str:
    """
    Mengunggah file (avatar atau gambar story) ke Supabase Storage.
    Jika Supabase Storage belum siap / offline / tanpa key,
    otomatis fallback ke folder static lokal (static/{folder}/{file_name}).
    Mengembalikan URL publik yang siap disimpan ke database dan ditampilkan di frontend.
    """
    # Pastikan data berupa bytes
    if hasattr(file_data, "read"):
        content_bytes = file_data.read()
    elif isinstance(file_data, bytes):
        content_bytes = file_data
    else:
        content_bytes = bytes(file_data)

    object_path = f"{folder}/{file_name}".strip("/")

    # 1. Coba upload ke Supabase Storage jika SUPABASE_URL & SUPABASE_KEY tersedia
    if SUPABASE_URL and SUPABASE_KEY and SUPABASE_KEY.startswith("eyJ"):
        try:
            upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET_NAME}/{object_path}"
            headers = {
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "apikey": SUPABASE_KEY,
                "Content-Type": content_type,
                "x-upsert": "true",
            }
            res = requests.post(upload_url, data=content_bytes, headers=headers, timeout=10)
            if res.status_code in (200, 201):
                public_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET_NAME}/{object_path}"
                print(f"[Supabase Storage] Upload sukses: {public_url}")
                return public_url
            else:
                print(f"[Supabase Storage] Response {res.status_code}: {res.text}. Menggunakan fallback lokal.")
        except Exception as e:
            print(f"[Supabase Storage] Gagal upload: {e}. Menggunakan fallback lokal.")

    # 2. Fallback Lokal (disimpan ke folder static/{folder}/)
    dest_dir = os.path.join(LOCAL_STATIC_DIR, folder)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, file_name)

    with open(dest_path, "wb") as f:
        f.write(content_bytes)

    local_url = f"/static/{folder}/{file_name}"
    print(f"[Local Storage Fallback] Disimpan ke {local_url}")
    return local_url

def upload_avatar(file_data, file_name: str, content_type: str = "image/png") -> str:
    """Helper untuk upload avatar profil"""
    return upload_file_to_storage(file_data, file_name, content_type, folder="avatars")

def upload_story_image(file_data, file_name: str, content_type: str = "image/png") -> str:
    """Helper untuk upload gambar / mockup user story"""
    return upload_file_to_storage(file_data, file_name, content_type, folder="story_images")