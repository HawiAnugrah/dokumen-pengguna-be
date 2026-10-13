# services/email.py
import os
import requests
from datetime import datetime

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "no-reply@userdoc.io")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "Userdoc Support")

def send_reset_password_email(to_email: str, reset_link: str) -> bool:
    """Mengirimkan email reset password ke inbox pengguna via Brevo API"""
    if not BREVO_API_KEY:
        print("⚠️ BREVO_API_KEY belum diisi di .env. Menggunakan fallback log console.")
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Reset Password - Userdoc</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 20px;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 30px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h2 style="color: #1e293b; margin-top: 0; text-align: center;">Permintaan Reset Password</h2>
            <p style="color: #475569; font-size: 14px; line-height: 1.6;">
                Halo, kami menerima permintaan untuk mengatur ulang kata sandi akun Userdoc Anda.
            </p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_link}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 14px; display: inline-block;">
                    Reset Password Saya
                </a>
            </div>
            <p style="color: #64748b; font-size: 12px; line-height: 1.5;">
                Tautan ini hanya berlaku selama <strong>15 menit</strong>. Jika Anda tidak merasa meminta reset password, silakan abaikan email ini.
            </p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
            <p style="color: #94a3b8; font-size: 11px; text-align: center; margin-bottom: 0;">
                &copy; 2026 Userdoc Application. All rights reserved.
            </p>
        </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": "Reset Password Akun Userdoc Anda",
        "htmlContent": html_content,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201, 202]:
            print(f"✅ Email reset password berhasil dikirim ke {to_email} via Brevo!")
            return True
        else:
            print(f"⚠️ Gagal kirim email via Brevo ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"⚠️ Error koneksi Brevo: {str(e)}")
        return False

def send_password_changed_notification(to_email: str, username: str) -> bool:
    """Mengirimkan email notifikasi konfirmasi bahwa kata sandi telah berhasil diubah via Brevo API"""
    if not BREVO_API_KEY:
        print("⚠️ BREVO_API_KEY belum diisi di .env. Menggunakan fallback log console.")
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    current_time_str = datetime.now().strftime("%d %b %Y, %H:%M WIB")

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Kata Sandi Berhasil Diubah - Userdoc</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 20px;">
        <div style="max-width: 520px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="display: inline-block; width: 48px; height: 48px; line-height: 48px; border-radius: 24px; background-color: #ecfdf5; color: #059669; font-size: 24px;">
                    🛡️
                </div>
                <h2 style="color: #1e293b; margin: 12px 0 4px 0; font-size: 20px;">Kata Sandi Berhasil Diubah</h2>
                <p style="color: #64748b; font-size: 13px; margin: 0;">Pemberitahuan Keamanan Akun Userdoc</p>
            </div>
            
            <p style="color: #334155; font-size: 14px; line-height: 1.6;">
                Halo <strong>{username}</strong>,
            </p>
            <p style="color: #475569; font-size: 14px; line-height: 1.6;">
                Kami ingin memberitahukan bahwa kata sandi untuk akun Anda (<strong>{to_email}</strong>) baru saja berhasil diperbarui pada <strong>{current_time_str}</strong>.
            </p>

            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; margin: 20px 0;">
                <p style="color: #64748b; font-size: 12px; margin: 0; line-height: 1.5;">
                    ℹ️ Jika Anda sendiri yang melakukan perubahan ini, Anda dapat mengabaikan email ini dengan aman.
                </p>
            </div>

            <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 14px; margin-bottom: 20px;">
                <p style="color: #b91c1c; font-size: 12px; margin: 0; line-height: 1.5; font-weight: 500;">
                    ⚠️ Jika Anda <strong>TIDAK</strong> merasa mengubah kata sandi ini, segera lakukan reset password menggunakan tautan lupa sandi atau hubungi administrator untuk mengamankan akun Anda.
                </p>
            </div>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
            <p style="color: #94a3b8; font-size: 11px; text-align: center; margin-bottom: 0;">
                &copy; 2026 Userdoc Application. Pesan otomatis dari sistem keamanan via Brevo.
            </p>
        </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": "[Keamanan Akun] Kata Sandi Akun Userdoc Anda Berhasil Diubah",
        "htmlContent": html_content,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201, 202]:
            print(f"✅ Email notifikasi perubahan kata sandi berhasil dikirim ke {to_email} via Brevo!")
            return True
        else:
            print(f"⚠️ Gagal kirim email perubahan kata sandi via Brevo ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"⚠️ Error koneksi Brevo saat kirim notifikasi: {str(e)}")
        return False

def send_otp_email(to_email: str, username: str, otp_code: str) -> bool:
    """Mengirimkan kode OTP verifikasi 6-digit ke email pengguna via Brevo API"""
    print(f"\n{'='*60}\n🔑 [OTP KEAMANAN USERDOC]\nPenerima: {to_email} ({username})\nKode OTP: {otp_code}\nMasa Berlaku: 10 Menit\n{'='*60}\n")
    if not BREVO_API_KEY:
        print("⚠️ BREVO_API_KEY belum diisi di .env. Kode OTP hanya dicatat di log server.")
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Kode Verifikasi OTP - Userdoc</title>
    </head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 20px;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; padding: 32px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <div style="text-align: center; margin-bottom: 24px;">
                <div style="display: inline-block; width: 50px; height: 50px; line-height: 50px; border-radius: 25px; background-color: #eff6ff; color: #2563eb; font-size: 26px;">
                    🔐
                </div>
                <h2 style="color: #1e293b; margin: 12px 0 4px 0; font-size: 20px;">Kode Verifikasi Keamanan</h2>
                <p style="color: #64748b; font-size: 13px; margin: 0;">Permintaan Pengubahan Kata Sandi Akun</p>
            </div>

            <p style="color: #334155; font-size: 14px; line-height: 1.6;">
                Halo <strong>{username}</strong>,
            </p>
            <p style="color: #475569; font-size: 14px; line-height: 1.6;">
                Kami menerima permintaan untuk mengubah kata sandi akun Anda (<strong>{to_email}</strong>). Masukkan 6-digit kode verifikasi (OTP) berikut untuk membuktikan kepemilikan akun Anda:
            </p>

            <div style="text-align: center; margin: 28px 0;">
                <div style="display: inline-block; background-color: #f8fafc; border: 2px dashed #3b82f6; border-radius: 12px; padding: 14px 32px; font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1d4ed8; font-family: monospace;">
                    {otp_code}
                </div>
                <p style="color: #64748b; font-size: 12px; margin-top: 10px;">
                    Kode ini hanya berlaku selama <strong>10 menit</strong>.
                </p>
            </div>

            <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 14px; margin-bottom: 20px;">
                <p style="color: #b91c1c; font-size: 12px; margin: 0; line-height: 1.5;">
                    ⚠️ <strong>PERINGATAN:</strong> Jangan pernah membagikan kode OTP ini kepada siapa pun, termasuk staf Userdoc. Jika Anda tidak melakukan permintaan ini, segera abaikan email ini dan kata sandi Anda tetap aman.
                </p>
            </div>

            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
            <p style="color: #94a3b8; font-size: 11px; text-align: center; margin-bottom: 0;">
                &copy; 2026 Userdoc Application. Verifikasi Keamanan Akun via Brevo.
            </p>
        </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": f"[Userdoc] {otp_code} adalah Kode Verifikasi Keamanan Anda",
        "htmlContent": html_content,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201, 202]:
            print(f"✅ Email kode OTP ({otp_code}) berhasil dikirim ke {to_email} via Brevo!")
            return True
        else:
            print(f"⚠️ Gagal kirim email OTP via Brevo ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"⚠️ Error koneksi Brevo saat kirim OTP: {str(e)}")
        return False
