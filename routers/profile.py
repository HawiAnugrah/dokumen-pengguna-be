from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from typing import Optional
import random
from datetime import datetime, timedelta, timezone

import model
import schemas
import auth
from database import get_db
from services.storage import upload_avatar  # <-- Impor helper upload MinIO kita
from services.email import send_otp_email, send_password_changed_notification


router = APIRouter(prefix="/api/profile", tags=["Profile"])

@router.get("", response_model=schemas.UserResponse)
def get_profile(current_user: model.User = Depends(auth.get_current_user)):
    """Mendapatkan informasi profil user yang sedang login"""
    return current_user

@router.put("", response_model=schemas.UserResponse)
def update_profile(
    profile_data: schemas.ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Mengubah info profil (nama lengkap)"""
    user = db.query(model.User).filter(model.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    if profile_data.full_name is not None:
        user.full_name = profile_data.full_name
    if profile_data.avatar_url is not None:
        user.avatar_url = profile_data.avatar_url
        
    db.commit()
    db.refresh(user)
    return user

@router.post("/avatar", response_model=schemas.UserResponse)
def upload_profile_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Mengunggah foto profil ke MinIO dan memperbarui URL avatar di database"""
    # 1. Validasi tipe file (harus berupa gambar)
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File yang diunggah harus berupa gambar (JPG, PNG, GIF)"
        )
    
    try:
        # 2. Baca data biner dari file
        file_content = file.file.read()
        
        # 3. Buat nama file unik berdasarkan ID pengguna agar tidak saling tindih
        file_ext = file.filename.split(".")[-1]  # mengambil ekstensi seperti png/jpg
        unique_filename = f"user_{current_user.id}_avatar.{file_ext}"
        
        # 4. Kirim file ke MinIO menggunakan helper
        avatar_url = upload_avatar(
            file_data=file_content,
            file_name=unique_filename,
            content_type=file.content_type
        )
        
        # 5. Simpan URL publik hasil upload ke database user
        user = db.query(model.User).filter(model.User.id == current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
        user.avatar_url = avatar_url
        db.commit()
        db.refresh(user)
        
        return user
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal mengunggah foto profil: {str(e)}"
        )

@router.post("/request-password-otp")
def request_password_otp(
    request_data: schemas.RequestPasswordOTP,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Meminta kode verifikasi 6-digit (OTP) via email untuk verifikasi pengubahan kata sandi"""
    # 1. Verifikasi kecocokan kata sandi lama
    if not auth.verify_password(request_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kata sandi saat ini tidak sesuai."
        )

    # 2. Nonaktifkan OTP lama yang belum terpakai untuk tujuan ini
    db.query(model.VerificationOTP).filter(
        model.VerificationOTP.user_id == current_user.id,
        model.VerificationOTP.purpose == "change_password",
        model.VerificationOTP.is_used == False
    ).update({"is_used": True})

    # 3. Generate 6-digit kode OTP acak
    otp_code = f"{random.randint(100000, 999999):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    new_otp = model.VerificationOTP(
        user_id=current_user.id,
        otp_code=otp_code,
        purpose="change_password",
        expires_at=expires_at,
        is_used=False
    )
    db.add(new_otp)
    db.commit()

    # 4. Kirim email OTP via Brevo
    display_name = current_user.full_name or current_user.username
    email_sent = send_otp_email(to_email=current_user.email, username=display_name, otp_code=otp_code)

    if not email_sent:
        return {
            "message": f"Kode OTP berhasil dibuat. Namun pengiriman email ke {current_user.email} tertahan oleh Brevo (Periksa otorisasi IP di Brevo). Anda dapat menyalin kode OTP langsung dari terminal backend."
        }

    return {
        "message": f"Kode verifikasi (OTP) telah dikirim ke {current_user.email}. Silakan cek kotak masuk atau folder spam Anda."
    }


@router.put("/change-password")
def change_password(
    password_data: schemas.PasswordUpdate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Mengubah kata sandi akun dengan validasi kata sandi lama dan kode OTP email"""
    # 1. Verifikasi apakah password lama cocok
    if not auth.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kata sandi saat ini tidak sesuai."
        )

    # 2. Verifikasi kode OTP
    if not password_data.otp_code or not password_data.otp_code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kode verifikasi (OTP) wajib diisi. Silakan minta kode OTP terlebih dahulu."
        )

    now = datetime.now(timezone.utc)
    otp_record = db.query(model.VerificationOTP).filter(
        model.VerificationOTP.user_id == current_user.id,
        model.VerificationOTP.purpose == "change_password",
        model.VerificationOTP.is_used == False,
        model.VerificationOTP.expires_at > now
    ).order_by(model.VerificationOTP.id.desc()).first()

    if not otp_record or otp_record.otp_code != password_data.otp_code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kode OTP tidak valid atau telah kedaluwarsa (berlaku 10 menit). Silakan minta kode OTP baru."
        )

    # Tandai OTP sudah digunakan
    otp_record.is_used = True

    # 3. Enkripsi dan simpan password baru ke user di database session aktif
    user = db.query(model.User).filter(model.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    user.hashed_password = auth.get_password_hash(password_data.new_password)
    db.commit()

    # 4. Kirim notifikasi keamanan via Brevo Email
    try:
        display_name = current_user.full_name or current_user.username
        send_password_changed_notification(to_email=current_user.email, username=display_name)
    except Exception as e:
        print(f"⚠️ Gagal mengirim notifikasi email Brevo: {str(e)}")

    return {"message": "Kata sandi berhasil diubah! Notifikasi keamanan telah dikirim ke email Anda."}