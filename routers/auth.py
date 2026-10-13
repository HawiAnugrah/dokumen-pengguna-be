from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from services.email import send_reset_password_email

import model
import schemas
import auth
from database import get_db

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    #  Periksa apakah email sudah terdaftar
    db_user_email = db.query(model.User).filter(model.User.email == user.email).first()
    if db_user_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email sudah terdaftar"
        )

    #  Periksa apakah username sudah terdaftar
    db_user_username = db.query(model.User).filter(model.User.username == user.username).first()
    if db_user_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username sudah terdaftar"
        )

    #  Hash password dan simpan user baru
    hashed_password = auth.get_password_hash(user.password)
    new_user = model.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login", response_model=schemas.Token)
def login(user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    #  Cari user berdasarkan email
    user = db.query(model.User).filter(model.User.email == user_credentials.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password salah"
        )
    
    #  Verifikasi password
    if not auth.verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau password salah"
        )
    
    #  Update data Last Login di database
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    # Buat token akses JWT & refresh token
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    refresh_token = auth.create_refresh_token(
        data={"sub": user.email}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
        "user": user
    }

@router.post("/refresh", response_model=schemas.TokenRefreshResponse)
def refresh_token(request: schemas.RefreshTokenRequest, db: Session = Depends(get_db)):
    """Memperbarui access token yang kedaluwarsa menggunakan refresh token yang valid."""
    email = auth.verify_refresh_token(request.refresh_token)
    user = db.query(model.User).filter(model.User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Pengguna tidak ditemukan."
        )

    new_access_token = auth.create_access_token(data={"sub": user.email})
    new_refresh_token = auth.create_refresh_token(data={"sub": user.email})

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "refresh_token": new_refresh_token
    }

@router.post("/forgot-password")
def forgot_password(request: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Cari user berdasarkan email
    user = db.query(model.User).filter(model.User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email tidak terdaftar"
        )
    #  Buat Token Reset JWT (Masa berlaku 15 menit)
    reset_token_expires = timedelta(minutes=15)
    reset_token = auth.create_access_token(
        data={"sub": user.email, "type": "reset"}, 
        expires_delta=reset_token_expires
    )
    
    #  Kirim Email Reset Password
    import os
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    reset_link = f"{frontend_url}/reset-password?token={reset_token}"
    
    # Kirim email asli via Brevo
    send_reset_password_email(to_email=user.email, reset_link=reset_link)

    print("\n" + "="*60)
    print("MOCK EMAIL SYSTEM - LINK RESET PASSWORD")
    print(f"Kirim Ke: {user.email}")
    print(f"Link Reset: {reset_link}")
    print("="*60 + "\n")
    return {"message": "Link reset password berhasil dikirim ke email"}
@router.post("/reset-password")
def reset_password(request: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Token reset tidak valid atau telah kedaluwarsa"
    )
    
    try:
        #  Dekode dan verifikasi token
        payload = jwt.decode(request.token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        # Validasi tipe token untuk memastikan ini adalah token reset
        if email is None or token_type != "reset":
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    #  Cari user yang memiliki email tersebut
    user = db.query(model.User).filter(model.User.email == email).first()
    if not user:
        raise credentials_exception
    #  Hash password baru dan simpan ke database
    user.hashed_password = auth.get_password_hash(request.new_password)
    db.commit()

    # Kirim notifikasi keamanan via Brevo Email
    try:
        from services.email import send_password_changed_notification
        display_name = user.full_name or user.username
        send_password_changed_notification(to_email=user.email, username=display_name)
    except Exception as e:
        print(f"⚠️ Gagal mengirim notifikasi email Brevo: {str(e)}")

    return {"message": "Password berhasil diperbarui dan notifikasi keamanan telah dikirim ke email"}