import os
import re
import json
import time
import threading
import itertools
from typing import List, Optional, Type, TypeVar, Union

from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

T = TypeVar("T", bound=BaseModel)

# ================= SKEMA OUTPUT TERSTRUKTUR UNTUK AI =================
class PersonaSuggestion(BaseModel):
    name: str = Field(description="Nama lengkap persona fiktif yang representatif (misal: Sarah Wijaya)")
    age: int = Field(description="Usia persona yang masuk akal untuk tipe pengguna ini")
    location: str = Field(description="Kota/lokasi tempat tinggal persona (contoh: Jakarta, Indonesia)")
    family_status: str = Field(description="Status keluarga singkat (misal: Menikah, punya 1 anak / Lajang)")
    job_title: str = Field(description="Jabatan/pekerjaan persona yang relevan dengan tipe pengguna ini")
    about: str = Field(description="Deskripsi singkat 2-3 kalimat tentang latar belakang dan keseharian persona ini")
    goals: str = Field(description="Tujuan spesifik persona ini saat menggunakan aplikasi, 1-2 kalimat")
    frustrations: str = Field(description="Hal yang membuat persona ini frustrasi jika kebutuhannya tidak terpenuhi, 1-2 kalimat")


class UserTypeSuggestion(BaseModel):
    name: str = Field(description="Nama tipe pengguna/persona (misal: Guest User, Admin, Pembeli)")
    description: str = Field(
        description=(
            "Penjelasan singkat dan padat, MAKSIMAL 3 kalimat (jangan lebih panjang dari itu): "
            "siapa mereka, apa peran utama mereka di aplikasi, dan tingkat akses mereka dibanding "
            "tipe user lain. Ini hanya ringkasan identitas — tujuan/motivasi detail mereka akan "
            "digali terpisah di tahap lain, jadi tidak perlu dijelaskan panjang lebar di sini."
        )
    )
    personas: List[PersonaSuggestion] = Field(
        min_length=1,
        max_length=1,
        description=(
            "WAJIB berisi TEPAT 1-3 contoh persona fiktif yang representatif untuk tipe pengguna ini "
            "(array ini TIDAK BOLEH kosong), supaya tim punya gambaran konkret siapa yang sebenarnya "
            "memakai fitur ini (bukan sekadar kategori abstrak). Buat persona yang realistis dan "
            "spesifik, bukan generik."
        )
    )

# ================= TAMBAHAN: AI DRAFT USER TYPE (dipakai UserTypes.tsx) =================
class UserTypeDraftSuggestion(BaseModel):
    name: str = Field(
        description=(
            "Nama satu tipe pengguna/persona yang relevan dan BELUM ada di daftar yang sudah "
            "dibuat (misal: Guest User, Admin, Pembeli, Penjual)."
        )
    )
    description: str = Field(
        description=(
            "Penjelasan singkat dan padat, MAKSIMAL 3 kalimat: siapa mereka, apa peran utama "
            "mereka di aplikasi, dan tingkat akses mereka dibanding tipe user lain."
        )
    )

def suggest_user_type_draft(
    project_name: str,
    project_description: str = "",
    application_type: str = "",
    domain_business: str = "",
    existing_user_types: Optional[List[str]] = None,
) -> UserTypeDraftSuggestion:
    """AI Draft: menyarankan SATU user type baru (name + description) untuk ditambahkan,
    dipakai tombol 'AI Draft' saat user klik 'Add user type' di step UserTypes."""
    existing_user_types = existing_user_types or []
    existing_line = (
        ", ".join(existing_user_types) if existing_user_types else "Belum ada tipe pengguna yang ditambahkan."
    )

    prompt = f"""
Kamu adalah Senior Business Analyst yang mengidentifikasi tipe pengguna (user type) untuk sebuah
proyek software.

Nama Proyek: {project_name}
Deskripsi: {project_description or 'Tidak ada deskripsi.'}
Tipe Aplikasi: {application_type or 'Tidak disebutkan'}
Domain Bisnis: {domain_business or 'Tidak disebutkan'}

Tipe pengguna yang SUDAH ada di proyek ini (JANGAN mengulang tipe ini, pilih tipe lain yang masih
relevan dan belum tercakup): {existing_line}

Tugasmu: sarankan SATU tipe pengguna baru yang paling penting untuk ditambahkan berikutnya, yang
belum ada di daftar di atas. Deskripsi cukup singkat (maksimal 3 kalimat): siapa mereka, peran
utama mereka, dan tingkat akses mereka dibanding tipe user lain.

Tulis dalam Bahasa Indonesia.
""".strip()

    try:
        return _generate_structured(prompt, UserTypeDraftSuggestion, temperature=0.5)
    except Exception as e:
        raise RuntimeError(f"Gagal generate draf tipe pengguna: {str(e)}") from e
    
class EpicSuggestion(BaseModel):
    name: str = Field(description="Kategori fitur besar/modul aplikasi (misal: Autentikasi, Katalog Produk)")
    description: str = Field(
        description=(
            "Deskripsi lengkap 4-6 kalimat yang mencakup: (1) tujuan bisnis epic ini secara jelas, "
            "(2) daftar konkret fitur/kemampuan utama yang termasuk di dalamnya (sebutkan beberapa "
            "nama fitur/layar spesifik, bukan cuma kategori umum), (3) batasan cakupan eksplisit — "
            "apa yang TIDAK termasuk di epic ini supaya tidak tumpang tindih dengan epic lain, dan "
            "(4) siapa saja user type yang akan berinteraksi dengan modul ini. Epic adalah unit kerja "
            "besar yang akan dipecah developer jadi banyak task, jadi harus cukup jelas cakupannya."
        )
    )

# ================= TAMBAHAN: AI DRAFT & REFINE EPIC (dipakai EpicsList.tsx) =================
class EpicDraftSuggestion(BaseModel):
    title: str = Field(
        description=(
            "Nama satu Epic/modul fitur besar yang relevan dan BELUM ada di daftar epic yang "
            "sudah dibuat (misal: Autentikasi, Katalog Produk, Manajemen Pesanan)."
        )
    )
    description: str = Field(
        description=(
            "Deskripsi lengkap 4-6 kalimat mencakup: (1) tujuan bisnis epic ini, (2) daftar "
            "konkret fitur/kemampuan utama di dalamnya (sebutkan nama fitur/layar spesifik), "
            "(3) batasan cakupan eksplisit agar tidak tumpang tindih dengan epic lain, dan "
            "(4) siapa saja user type yang berinteraksi dengan modul ini."
        )
    )


class EpicRefineSuggestion(BaseModel):
    title: str = Field(description="Judul epic, boleh sama atau sedikit dirapikan dari input")
    description: str = Field(
        description=(
            "Versi deskripsi yang sudah disempurnakan: lebih detail dan konkret (fitur/layar "
            "spesifik disebutkan, batasan cakupan jelas, user type terkait disebutkan). "
            "Pertahankan maksud asli dari draf user, jangan ganti topiknya."
        )
    )

def suggest_epic_draft(
    project_name: str,
    project_description: str = "",
    application_type: str = "",
    domain_business: str = "",
    existing_epics: Optional[List[str]] = None,
) -> EpicDraftSuggestion:
    """AI Draft: menyarankan SATU epic baru (title + description) untuk ditambahkan,
    dipakai tombol 'AI Draft' saat user klik 'Add epic' di step EpicsList."""
    existing_epics = existing_epics or []
    existing_line = (
        ", ".join(existing_epics) if existing_epics else "Belum ada epic yang ditambahkan."
    )

    prompt = f"""
Kamu adalah Senior Business Analyst dan Solutions Architect yang menyusun Epic (modul fitur besar)
untuk sebuah proyek software.

Nama Proyek: {project_name}
Deskripsi: {project_description or 'Tidak ada deskripsi.'}
Tipe Aplikasi: {application_type or 'Tidak disebutkan'}
Domain Bisnis: {domain_business or 'Tidak disebutkan'}

Epic yang SUDAH ada di proyek ini (JANGAN mengulang epic ini, pilih modul lain yang masih relevan
dan belum tercakup): {existing_line}

Tugasmu: sarankan SATU epic baru yang paling penting untuk ditambahkan berikutnya, yang belum ada
di daftar di atas. Deskripsi harus detail dan konkret (sebutkan fitur/layar spesifik), punya
batasan cakupan yang jelas, dan menyebutkan user type yang terkait.

Tulis dalam Bahasa Indonesia.
""".strip()

    try:
        return _generate_structured(prompt, EpicDraftSuggestion, temperature=0.5)
    except Exception as e:
        raise RuntimeError(f"Gagal generate draf epic: {str(e)}") from e


def suggest_epic_refinement(
    title: str,
    description: str = "",
    project_name: str = "",
) -> EpicRefineSuggestion:
    """AI Suggest/Refine: menyempurnakan epic yang SUDAH ada (title + description),
    dipakai tombol 'AI Suggest' saat user mode edit epic di EpicsList."""
    prompt = f"""
Kamu adalah Senior Business Analyst dan Solutions Architect yang menyempurnakan Epic (modul fitur
besar) untuk sebuah proyek software.

Nama Proyek: {project_name or 'Tidak disebutkan'}
Judul Epic: {title}
Draf Deskripsi Saat Ini: {description or '(kosong, belum ditulis user)'}

Tugasmu: sempurnakan deskripsi epic ini agar lebih detail dan konkret — sebutkan fitur/layar
spesifik yang termasuk di dalamnya, batasan cakupan eksplisit (apa yang TIDAK termasuk supaya
tidak tumpang tindih dengan epic lain), dan user type yang berinteraksi dengan modul ini. Jangan
mengubah topik/maksud aslinya. Jika deskripsi saat ini kosong atau terlalu singkat, tulis dari
awal berdasarkan judul yang diberikan.

Tulis dalam Bahasa Indonesia.
""".strip()

    try:
        return _generate_structured(prompt, EpicRefineSuggestion, temperature=0.4)
    except Exception as e:
        raise RuntimeError(f"Gagal menyempurnakan epic: {str(e)}") from e
    
class UserStorySuggestion(BaseModel):
    epic_name: str = Field(description="Nama Epic tempat story ini bernaung (harus cocok persis dengan salah satu nama Epic di atas)")
    story_name: str = Field(description="Judul singkat cerita pengguna (misal: Registrasi Akun, Cari Produk Berdasarkan Kategori)")
    user_type: str = Field(description="Nama tipe pengguna yang melakukan aksi ini (harus cocok persis dengan salah satu User Type di atas)")
    description: str = Field(
        description=(
            "Deskripsi lengkap minimal 4-6 kalimat dengan struktur berikut, semua dalam satu paragraf "
            "naratif (bukan bullet list):\n"
            "(1) Format inti: 'Sebagai [user_type], saya ingin [aksi spesifik], agar [manfaat/tujuan bisnis "
            "yang jelas dan terukur]'.\n"
            "(2) Alur utama (main flow): jelaskan langkah demi langkah yang dilalui user dari mulai sampai "
            "selesai (misal: user membuka halaman X, mengisi form Y, menekan tombol Z, sistem memvalidasi, "
            "sistem menampilkan konfirmasi).\n"
            "(3) Minimal 1-2 kondisi khusus/edge case yang relevan dan bagaimana sistem seharusnya "
            "berperilaku (misal: input tidak valid, data kosong, koneksi gagal, duplikasi data, batas "
            "kuota tercapai, permission ditolak).\n"
            "(4) Ketergantungan/prasyarat jika ada (misal: 'story ini membutuhkan user sudah login' atau "
            "'membutuhkan data dari story lain terlebih dahulu')."
        )
    )
    acceptance_criteria: List[str] = Field(
        default_factory=list,
        description="2-4 kriteria penerimaan terukur dalam format Given-When-Then."
    )
    tech_notes: List[str] = Field(
        default_factory=list,
        description="2-4 catatan teknis implementasi database, API, atau keamanan."
    )
    test_cases: List[str] = Field(
        default_factory=list,
        description="2-4 skenario pengujian QA konkret."
    )

class NFRSuggestion(BaseModel):
    category: str = Field(
        default="General",
        description="Kategori NFR (Performance, Security, Availability, Usability, Scalability)."
    )
    description: str = Field(
        default="",
        description="Detail kebutuhan non-fungsional terukur."
    )

class UserJourneyStepSuggestion(BaseModel):
    title: str = Field(description="Judul singkat tahapan ini (misal: 'Membuka Halaman Utama', 'Mengisi Formulir Pendaftaran')")
    description: str = Field(
        description=(
            "Penjelasan detail 2-3 kalimat mengenai aksi konkret yang dilakukan pengguna pada tahap ini. "
            "Sebutkan halaman, komponen UI, atau tombol spesifik yang diklik, serta bagaimana sistem merespons aksi tersebut."
        )
    )
    persona_name: str = Field(
        description=(
            "Nama persona (dari daftar persona yang diberikan) yang melakukan aksi pada tahap ini. "
            "HARUS persis sama (termasuk huruf besar/kecil) dengan salah satu nama di daftar persona."
        )
    )

class UserJourneySuggestion(BaseModel):
    narrative: str = Field(
        description=(
            "Satu paragraf naratif (5-7 kalimat) yang menggambarkan keseluruhan alur pengalaman pengguna "
            "secara profesional dan mengalir dari awal penggunaan hingga tujuan tercapai."
        )
    )
    steps: List[UserJourneyStepSuggestion] = Field(
        description="5-7 tahapan berurutan dari awal (start) sampai akhir (end), masing-masing di-assign ke satu persona."
    )

class StoryDraftSuggestion(BaseModel):
    story_name: str = Field(description="Judul cerita pengguna yang spesifik terhadap aksi peran ini (misal: 'Filter Kandidat Berdasarkan Keahlian')")
    description: str = Field(
        description=(
            "Narasi user story terstruktur 2-3 kalimat: "
            "'Sebagai [user_type], saya ingin [aksi spesifik], agar [manfaat & tujuan bisnis terukur]'. "
            "Jelaskan juga alur singkat dan respons sistem."
        )
    )

class ProjectRequirementsOutput(BaseModel):
    user_types: List[UserTypeSuggestion] = Field(
        min_length=1,
        default_factory=list,
        description="Daftar 2-3 tipe pengguna utama beserta persona ringkasnya."
    )
    epics: List[EpicSuggestion] = Field(
        min_length=1,
        default_factory=list,
        description="Daftar 3-5 Epic modul fitur utama aplikasi."
    )
    user_stories: List[UserStorySuggestion] = Field(
        default_factory=list,
        description="Daftar User Story awal (bisa kosong dan ditambahkan nanti per-modul)."
    )
    nfrs: List[NFRSuggestion] = Field(
        default_factory=list,
        description="Daftar 3-5 Non-Functional Requirements (NFR) wajib mencakup Performance, Security, Reliability, dan Usability dengan target kuantitatif terukur."
    )
    user_journey: Optional[UserJourneySuggestion] = Field(
        default=None,
        description="Alur narasi dan langkah User Journey menyeluruh (5-7 tahapan langkah terstruktur)."
    )

# ================= TAMBAHAN: AI DRAFT & REFINE NFR (dipakai NonFunctionalList.tsx) =================

class NFRDraftSuggestion(BaseModel):
    category: str = Field(
        description=(
            "Satu kategori NFR yang relevan dan BELUM ada di daftar kategori yang sudah dipakai "
            "(contoh: Performance, Security, Availability, Usability, Scalability, Compliance, "
            "Maintainability, Compatibility, Data Integrity)."
        )
    )
    description: str = Field(
        description=(
            "Detail kebutuhan non-fungsional dengan TARGET KUANTITATIF/TERUKUR yang jelas, "
            "kontekstual terhadap proyek ini. Hindari deskripsi generik seperti 'harus cepat' "
            "atau 'harus aman' tanpa angka/standar yang jelas."
        )
    )


class NFRRefineSuggestion(BaseModel):
    category: str = Field(description="Nama kategori NFR, boleh sama atau sedikit dirapikan dari input")
    description: str = Field(
        description=(
            "Versi deskripsi yang sudah disempurnakan: lebih spesifik, terukur (ada target "
            "kuantitatif), dan jelas cara verifikasinya. Pertahankan maksud asli dari draf user, "
            "jangan ganti topiknya."
        )
    )

def suggest_nfr_draft(
    project_name: str,
    project_description: str = "",
    application_type: str = "",
    domain_business: str = "",
    existing_categories: Optional[List[str]] = None,
) -> NFRDraftSuggestion:
    """AI Draft: menyarankan SATU NFR baru (kategori + deskripsi) untuk ditambahkan,
    dipakai tombol 'AI Draft' saat user klik 'Add requirement' di step NonFunctionalList."""
    existing_categories = existing_categories or []
    existing_line = (
        ", ".join(existing_categories) if existing_categories else "Belum ada NFR yang ditambahkan."
    )

    prompt = f"""
Kamu adalah Senior Business Analyst yang menyusun Non-Functional Requirements (NFR) untuk proyek software.

Nama Proyek: {project_name}
Deskripsi: {project_description or 'Tidak ada deskripsi.'}
Tipe Aplikasi: {application_type or 'Tidak disebutkan'}
Domain Bisnis: {domain_business or 'Tidak disebutkan'}

Kategori NFR yang SUDAH ada di proyek ini (JANGAN mengulang kategori ini, pilih kategori lain yang
masih relevan dan belum tercakup): {existing_line}

Tugasmu: sarankan SATU NFR baru yang paling penting untuk ditambahkan berikutnya, dengan kategori
yang belum ada di daftar di atas. Deskripsi harus punya target kuantitatif/terukur yang jelas dan
kontekstual terhadap proyek ini.

Tulis dalam Bahasa Indonesia.
""".strip()

    try:
        return _generate_structured(prompt, NFRDraftSuggestion, temperature=0.5)
    except Exception as e:
        raise RuntimeError(f"Gagal generate draf NFR: {str(e)}") from e


def suggest_nfr_refinement(
    category: str,
    description: str = "",
    project_name: str = "",
) -> NFRRefineSuggestion:
    """AI Suggest/Refine: menyempurnakan NFR yang SUDAH ada (kategori + deskripsi),
    dipakai tombol 'AI Suggest' saat user mode edit NFR di NonFunctionalList."""
    prompt = f"""
Kamu adalah Senior Business Analyst yang menyempurnakan Non-Functional Requirements (NFR) untuk
proyek software.

Nama Proyek: {project_name or 'Tidak disebutkan'}
Kategori NFR: {category}
Draf Deskripsi Saat Ini: {description or '(kosong, belum ditulis user)'}

Tugasmu: sempurnakan deskripsi NFR ini agar lebih spesifik, jelas, dan TERUKUR (punya target
kuantitatif/angka konkret serta cara verifikasinya), tanpa mengubah topik/maksud aslinya. Jika
deskripsi saat ini kosong atau terlalu singkat, tulis dari awal berdasarkan kategori yang diberikan.

Tulis dalam Bahasa Indonesia.
""".strip()

    try:
        return _generate_structured(prompt, NFRRefineSuggestion, temperature=0.4)
    except Exception as e:
        raise RuntimeError(f"Gagal menyempurnakan NFR: {str(e)}") from e
    
# ================= TAMBAHAN: SARAN GOALS & FRUSTRATIONS PER USER TYPE =================

class UserGoalsSuggestion(BaseModel):
    goals: str = Field(
        description=(
            "Tujuan utama tipe pengguna ini saat memakai aplikasi, ditulis 2-3 kalimat yang "
            "spesifik dan kontekstual terhadap nama proyek serta peran user tersebut — bukan "
            "kalimat generik yang bisa berlaku untuk aplikasi apa saja."
        )
    )
    frustrations: str = Field(
        description=(
            "Hal-hal yang membuat tipe pengguna ini frustrasi saat memakai aplikasi sejenis, "
            "ditulis 2-3 kalimat yang spesifik dan kontekstual terhadap peran user tersebut — "
            "bukan kalimat generik seperti 'UI membingungkan' tanpa konteks."
        )
    )

def suggest_story_draft(
    project_name: str,
    epic_title: str,
    user_type: str,
    project_description: str = "",
) -> StoryDraftSuggestion:
    """AI Draft User Story yang spesifik terhadap peranan user_type dan modul/epic terkait."""
    prompt = f"""
Kamu adalah Senior Agile Product Owner yang menyusun User Story konkret untuk sebuah proyek software.

Nama Proyek: {project_name}
Deskripsi Proyek: {project_description or 'Tidak ada deskripsi.'}
Modul/Epic: {epic_title}
Tipe Pengguna (User Type): {user_type}

Tugasmu:
Buatkan SATU User Story yang sangat relevan, konkret, dan spesifik untuk tipe pengguna "{user_type}" di dalam modul/epic "{epic_title}".
Format deskripsi WAJIB:
"Sebagai {user_type}, saya ingin [aksi/fitur spesifik], agar [manfaat & nilai bisnis terukur]."
Sertakan juga ringkasan alur aksi pengguna dan respons sistem (2-3 kalimat total).

Tulis dalam Bahasa Indonesia yang profesional.
""".strip()

    try:
        return _generate_structured(prompt, StoryDraftSuggestion, temperature=0.5)
    except Exception as e:
        raise RuntimeError(f"Gagal generate draf user story: {str(e)}") from e

class TechStackSuggestion(BaseModel):
    target_users: str = Field(description="Perkiraan skala/segmen target pengguna aplikasi (contoh: '1.000 - 10.000 pengguna aktif bulanan')")
    scale: str = Field(description="Perkiraan skala sistem yang dibutuhkan (contoh: 'Small to Medium Scale')")
    platform: str = Field(description="Pendekatan pengembangan/platform yang direkomendasikan (contoh: 'Web-based, AI-assisted development dengan Claude Code/Cursor')")
    ui_language: str = Field(description="Bahasa pemrograman utama untuk UI Layer (contoh: 'TypeScript')")
    ui_framework: str = Field(description="Framework UI (contoh: 'Next.js (React)')")
    ui_library: str = Field(description="Library/komponen UI (contoh: 'Tailwind CSS + shadcn/ui')")
    app_language: str = Field(description="Bahasa pemrograman backend (contoh: 'Python')")
    app_framework: str = Field(description="Framework backend (contoh: 'FastAPI')")
    data_layer: str = Field(description="Database utama (contoh: 'PostgreSQL')")
    integration_layer: str = Field(description="Protokol/pola integrasi (contoh: 'REST API + Webhooks')")


class GuidelineSuggestion(BaseModel):
    title: str = Field(description="Judul singkat guideline (contoh: 'Struktur Folder & Penamaan File')")
    content: str = Field(
        description=(
            "Isi guideline 3-5 kalimat yang actionable dan spesifik terhadap tech stack proyek "
            "ini -- bukan saran generik yang berlaku untuk semua bahasa pemrograman."
        )
    )


class CodingGuidelinesSuggestion(BaseModel):
    guidelines: List[GuidelineSuggestion] = Field(
        description="3-5 coding guideline paling penting untuk proyek ini, spesifik terhadap tech stack yang dipakai."
    )

class DevPlanItemSuggestion(BaseModel):
    title: str = Field(description="Judul task pengembangan (contoh: 'Implementasi Autentikasi & Registrasi')")
    description: str = Field(description="Deskripsi singkat 1-2 kalimat cakupan task ini")

class DevPlanSuggestion(BaseModel):
    items: List[DevPlanItemSuggestion] = Field(
        description="Daftar task pengembangan awal, satu task per Epic yang diberikan, dengan urutan prioritas logis (fondasi/autentikasi duluan)."
    )

class DevPlanDetailSuggestion(BaseModel):
    title: str = Field(description="Judul task development, boleh mengikuti nama epic")
    description: str = Field(
        description=(
            "Rencana pengembangan yang detail dan actionable untuk dipakai AI coding agent langsung "
            "mengimplementasikan epic ini. Sertakan: (1) ringkasan cakupan kerja, (2) daftar langkah "
            "implementasi berurutan, (3) catatan teknis penting (mengacu ke tech stack & coding "
            "guidelines proyek bila relevan), (4) definisi selesai (definition of done)."
        )
    )

# ================= TAMBAHKAN skema ini di dekat skema-skema lain (bagian atas) =================

class AIRuleSuggestionItem(BaseModel):
    name: str = Field(
        description="Judul singkat aturan (misal: 'Gaya Bahasa Formal', 'Format User Story Wajib Bahasa Indonesia')"
    )
    content: str = Field(
        description=(
            "Isi aturan yang jelas dan actionable, 2-4 kalimat, spesifik terhadap konteks proyek ini "
            "-- bukan saran generik yang bisa berlaku untuk proyek apa saja."
        )
    )


class AIRuleSuggestionsOutput(BaseModel):
    rules: List[AIRuleSuggestionItem] = Field(
        description=(
            "3-5 saran AI Rules yang relevan dan spesifik untuk proyek ini. Cakup aspek-aspek seperti "
            "gaya bahasa/istilah yang dipakai, format penulisan user story, tingkat detail teknis yang "
            "diharapkan, konvensi penamaan, batasan cakupan, atau standar kepatuhan/regulasi yang "
            "relevan dengan domain bisnis proyek ini."
        )
    )

# ================= TAMBAHKAN fungsi ini di dekat fungsi suggest_* lainnya =================

def suggest_ai_rules(
    project_name: str,
    project_description: str,
    application_type: str = "",
    domain_business: str = "",
) -> AIRuleSuggestionsOutput:
    """Menyarankan beberapa draf AI Rules untuk sebuah project, dipakai tombol
    'Generate' di tab AI Rules halaman Settings."""
    prompt = f"""
Kamu adalah Senior Business Analyst yang membantu menyusun AI Rules -- instruksi khusus yang akan
memandu AI dalam men-generate dokumentasi kebutuhan software (user story, persona, journey, NFR, dsb)
untuk sebuah proyek.

Nama Proyek: {project_name}
Deskripsi: {project_description or 'Tidak ada deskripsi.'}
Tipe Aplikasi: {application_type or 'Tidak disebutkan'}
Domain Bisnis: {domain_business or 'Tidak disebutkan'}

Sarankan 3-5 AI Rules yang relevan dan spesifik untuk proyek ini. Setiap rule harus actionable dan
bisa langsung memandu AI, contoh topik: gaya bahasa/istilah yang dipakai, format penulisan user story,
tingkat detail teknis yang diharapkan, konvensi penamaan, batasan cakupan tertentu, atau standar
kepatuhan/regulasi yang relevan dengan domain bisnis ini. Hindari saran generik yang bisa berlaku
untuk proyek apa saja.

Tulis dalam Bahasa Indonesia.
""".strip()

    try:
        return _generate_structured(prompt, AIRuleSuggestionsOutput, temperature=0.5)
    except Exception as e:
        raise RuntimeError(f"Gagal memanggil AI: {str(e)}")
    
# ================= KONFIGURASI PROVIDER AI =================
raw_gemini_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEYS = [k.strip() for k in re.split(r"[,;\n]+", raw_gemini_keys) if k.strip()]
_primary_gemini_model = os.getenv("GEMINI_MODEL_NAME") or os.getenv("GEMINI_MODEL") or "gemini-2.0-flash"
GEMINI_MODELS = list(dict.fromkeys([
    _primary_gemini_model,
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-flash-latest",
    "gemini-3.8-flash",
]))
GEMINI_MODEL = GEMINI_MODELS[0]

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL_NAME", "nvidia/nemotron-3.5-lightning:free")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
_primary_groq_model = os.getenv("GROQ_MODEL_NAME") or "qwen/qwen3.8-27b"
GROQ_MODELS = list(dict.fromkeys([
    _primary_groq_model,
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]))
GROQ_MODEL = GROQ_MODELS[0]

gemini_clients = [genai.Client(api_key=k) for k in GEMINI_API_KEYS]
gemini_client = gemini_clients[0] if gemini_clients else None
openrouter_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL, timeout=None) if OPENROUTER_API_KEY else None
groq_client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL, timeout=None) if GROQ_API_KEY else None

_PROVIDER_NAMES = ["gemini", "openrouter", "groq"]
_provider_cycle = itertools.cycle(_PROVIDER_NAMES)
_cycle_lock = threading.Lock()
_gemini_cooldown_until = 0.0


def _next_provider_order() -> List[str]:
    """Coba Gemini terlebih dahulu (jika tidak sedang cooldown kuota/503).
    Jika Gemini sedang limit/down, utamakan Groq agar respons instan (<1 detik)."""
    global _gemini_cooldown_until
    now = time.time()
    gemini_available = bool(gemini_clients) and (now >= _gemini_cooldown_until)

    providers = []
    if gemini_available:
        providers.append("gemini")
    if groq_client:
        providers.append("groq")
    if not gemini_available and gemini_clients:
        providers.append("gemini")
    if openrouter_client:
        providers.append("openrouter")
    return providers if providers else ["groq"]


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(text: str) -> str:
    """Bersihkan output model non-Gemini yang kadang membungkus JSON dengan
    code fence atau menambahkan kalimat pembuka/penutup di luar JSON."""
    candidate = _strip_json_fence(text)
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        return candidate[start:end + 1]
    return candidate


_active_gemini_key_idx = 0
_key_lock = threading.Lock()

def _call_gemini(prompt: str, schema: Type[T], temperature: float, max_output_tokens: Optional[int] = None) -> T:
    global _active_gemini_key_idx
    if not gemini_clients:
        raise RuntimeError("GEMINI_API_KEY tidak diset di .env")

    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    system_msg = (
        "Kamu adalah asisten yang WAJIB membalas HANYA dengan satu objek JSON valid yang "
        "sesuai skema berikut, tanpa teks pembuka, tanpa penjelasan, tanpa markdown code fence:\n\n"
        f"{schema_json}"
    )

    config_kwargs = dict(
        response_mime_type="application/json",
        temperature=temperature,
        system_instruction=system_msg,
    )
    if max_output_tokens:
        config_kwargs["max_output_tokens"] = min(max_output_tokens, 8192)

    total_keys = len(gemini_clients)
    errors = []
    quota_exhausted = False
    for model_name in GEMINI_MODELS:
        if quota_exhausted:
            break
        consecutive_503 = 0
        consecutive_quota = 0
        for offset in range(total_keys):
            with _key_lock:
                idx = (_active_gemini_key_idx + offset) % total_keys
            client = gemini_clients[idx]

            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )

                finish_reason = None
                try:
                    finish_reason = response.candidates[0].finish_reason
                except Exception:
                    pass
                if finish_reason is not None and str(finish_reason).upper().find("MAX_TOKENS") != -1:
                    raise RuntimeError("Respons Gemini terpotong karena melebihi batas token maksimum.")

                raw_text = (response.text or "").strip()
                candidate = _extract_json_object(raw_text)
                result_json = json.loads(candidate)
                return schema(**result_json)
            except Exception as e:
                err_str = str(e).lower()
                is_404 = "404" in err_str or "not found" in err_str or "no longer available" in err_str or "not supported" in err_str
                is_503 = "503" in err_str or "demand" in err_str or "unavailable" in err_str
                is_quota = "429" in err_str or "quota" in err_str or "exhausted" in err_str or "rate" in err_str

                # Jika model 404 (tidak ada/deprecated di Google), langsung skip model ini tanpa buang waktu coba key lain
                if is_404:
                    errors.append(f"[Gemini {model_name}] 404 Model tidak tersedia")
                    break

                # Jika key kehabisan RPD/kuota harian, geser pointer ke key berikutnya
                if is_quota:
                    consecutive_quota += 1
                    with _key_lock:
                        _active_gemini_key_idx = (idx + 1) % total_keys
                    if consecutive_quota >= 2:
                        errors.append(f"[Gemini {model_name}] Quota project habis pada 2 key berturut-turut")
                        quota_exhausted = True
                        break
                else:
                    consecutive_quota = 0

                errors.append(f"[Gemini {model_name} Key #{idx+1}] {e}")

                if is_503:
                    consecutive_503 += 1
                    # Jika 2 key berturut-turut kena 503 (server Google sedang overload), langsung fallback ke Groq
                    if consecutive_503 >= 2:
                        break
                else:
                    consecutive_503 = 0

    global _gemini_cooldown_until
    with _key_lock:
        _gemini_cooldown_until = time.time() + 180  # Cooldown 3 menit agar request berikutnya instan lewat Groq

    raise RuntimeError("Semua Gemini API Key & Model gagal: " + " || ".join(errors))


def _call_gemini_text(prompt: str, temperature: float = 0.5) -> str:
    global _active_gemini_key_idx
    if not gemini_clients:
        raise RuntimeError("GEMINI_API_KEY tidak diset di .env")

    total_keys = len(gemini_clients)
    errors = []
    quota_exhausted = False
    for model_name in GEMINI_MODELS:
        if quota_exhausted:
            break
        consecutive_503 = 0
        consecutive_quota = 0
        for offset in range(total_keys):
            with _key_lock:
                idx = (_active_gemini_key_idx + offset) % total_keys
            client = gemini_clients[idx]

            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=temperature),
                )
                text = (response.text or "").strip()
                if text:
                    return text
            except Exception as e:
                err_str = str(e).lower()
                is_404 = "404" in err_str or "not found" in err_str or "no longer available" in err_str or "not supported" in err_str
                is_503 = "503" in err_str or "demand" in err_str or "unavailable" in err_str
                is_quota = "429" in err_str or "quota" in err_str or "exhausted" in err_str or "rate" in err_str

                if is_404:
                    errors.append(f"[Gemini {model_name}] 404 Model tidak tersedia")
                    break

                if is_quota:
                    consecutive_quota += 1
                    with _key_lock:
                        _active_gemini_key_idx = (idx + 1) % total_keys
                    if consecutive_quota >= 2:
                        errors.append(f"[Gemini {model_name}] Quota project habis pada 2 key berturut-turut")
                        quota_exhausted = True
                        break
                else:
                    consecutive_quota = 0

                errors.append(f"[Gemini {model_name} Key #{idx+1}] {e}")

                if is_503:
                    consecutive_503 += 1
                    if consecutive_503 >= 2:
                        break
                else:
                    consecutive_503 = 0

    global _gemini_cooldown_until
    with _key_lock:
        _gemini_cooldown_until = time.time() + 180  # Cooldown 3 menit agar request berikutnya instan lewat Groq

    raise RuntimeError("Semua Gemini API Key & Model gagal untuk teks: " + " || ".join(errors))


def _call_openai_compatible(
    client: Optional[OpenAI],
    models: Union[str, List[str]],
    prompt: str,
    schema: Type[T],
    temperature: float,
    max_tokens: Optional[int] = None,
) -> T:
    model_list = [models] if isinstance(models, str) else models
    if client is None:
        raise RuntimeError(f"API key untuk model '{model_list[0]}' tidak diset di .env")

    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    system_msg = (
        "Kamu adalah asisten yang WAJIB membalas HANYA dengan satu objek JSON valid yang "
        "sesuai skema berikut, tanpa teks pembuka, tanpa penjelasan, tanpa markdown code fence:\n\n"
        f"{schema_json}"
    )

    errors = []
    for model in model_list:
        create_kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=min(max_tokens or 4096, 4096),
        )

        try:
            try:
                response = client.chat.completions.create(response_format={"type": "json_object"}, **create_kwargs)
            except Exception:
                response = client.chat.completions.create(**create_kwargs)

            choice = response.choices[0]
            raw_text = (choice.message.content or "").strip()
            candidate = _extract_json_object(raw_text)
            result_json = json.loads(candidate)
            return schema(**result_json)
        except Exception as e:
            errors.append(f"[{model}] {e}")
            continue

    raise RuntimeError("Semua model gagal: " + " || ".join(errors))

def _generate_structured(prompt: str, schema: Type[T], temperature: float = 0.3, max_tokens: Optional[int] = None) -> T:
    """
    Dispatcher utama untuk semua generate yang butuh output terstruktur (JSON -> Pydantic).
    Urutan provider mengikuti round-robin (_next_provider_order), dengan fallback otomatis
    ke provider berikutnya kalau salah satu gagal.
    """
    errors: List[str] = []
    for provider in _next_provider_order():
        try:
            if provider == "gemini":
                return _call_gemini(prompt, schema, temperature, max_output_tokens=max_tokens)
            elif provider == "groq":
                return _call_openai_compatible(
                    groq_client, GROQ_MODELS, prompt, schema, temperature, max_tokens=max_tokens
                )
            elif provider == "openrouter":
                return _call_openai_compatible(
                    openrouter_client, OPENROUTER_MODEL, prompt, schema, temperature, max_tokens=max_tokens
                )
        except Exception as e:
            errors.append(f"[{provider}] {e}")
            continue

    raise RuntimeError(
        "Semua provider AI (Gemini, OpenRouter, Groq) gagal merespons secara bergiliran. "
        "Detail per provider: " + " || ".join(errors)
    )

def _generate_text(prompt: str, temperature: float = 0.5) -> str:
    """Dispatcher untuk generate teks bebas (non-JSON), dengan round-robin + fallback yang sama."""
    errors: List[str] = []
    for provider in _next_provider_order():
        try:
            if provider == "gemini":
                text = _call_gemini_text(prompt, temperature=temperature)
            else:
                client = openrouter_client if provider == "openrouter" else groq_client
                model = OPENROUTER_MODEL if provider == "openrouter" else GROQ_MODEL
                if client is None:
                    raise RuntimeError(f"API key untuk provider '{provider}' tidak diset di .env")
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                )
                text = (response.choices[0].message.content or "").strip()

            if not text:
                raise RuntimeError(f"Respons kosong dari provider '{provider}'")
            return text
        except Exception as e:
            errors.append(f"[{provider}] {e}")
            continue

    raise RuntimeError(
        "Semua provider AI (Gemini, OpenRouter, Groq) gagal merespons secara bergiliran. "
        "Detail per provider: " + " || ".join(errors)
    )


# ================= FUNGSI-FUNGSI GENERATE (PUBLIC API) =================

def generate_project_requirements(
    project_name: str,
    project_description: str,
    application_type: str,
    domain_business: str,
    target_users: str,
    business_goals: str,
    ai_rules: List[str]
) -> ProjectRequirementsOutput:
    """
    Menghasilkan draf dokumentasi kebutuhan software yang detail dan siap dipakai
    developer — mencakup user types, epics, user stories (dengan acceptance criteria,
    tech notes, dan test cases), serta NFR. Provider dipilih bergiliran (round-robin)
    dengan fallback otomatis kalau salah satu provider gagal/limit/output terpotong.
    """
    if ai_rules:
        rules_prompt = "\n".join([f"- {rule}" for rule in ai_rules])
    else:
        rules_prompt = "- Tidak ada aturan khusus. Tulis dengan standar profesional umum."

    prompt = f"""
    Anda adalah seorang Senior Business Analyst dan Solutions Architect dengan pengalaman lebih dari
    10 tahun menulis dokumentasi kebutuhan software untuk tim engineering profesional.

    DETAIL PROYEK:
    Nama Proyek: {project_name}
    Deskripsi: {project_description}
    Tipe Aplikasi: {application_type}
    Domain Bisnis: {domain_business}
    Target Pengguna: {target_users}
    Tujuan Bisnis: {business_goals}

    ATURAN KHUSUS AI (WAJIB DIPATUHI):
    {rules_prompt}

    INSTRUKSI PENYUSUNAN (LENGKAP, KAYA, & BERVARIASI):

    1. USER TYPES (2 - 3 tipe pengguna)
        - Identifikasi 2 sampai 3 tipe pengguna yang berbeda peran dan hak aksesnya (misal: Pelamar/Pencari Kerja, Perekrut/Perusahaan, Administrator).
        - Deskripsi singkat (2-3 kalimat) mengenai peran, tanggung jawab, dan tingkat hak aksesnya di aplikasi.
        - Setiap User Type WAJIB menyertakan 1 persona fiktif konkret.
        - FIELD GOALS: Tuliskan minimal 2 sampai 3 poin tujuan konkret menggunakan bullet points (contoh: "• Menemukan lowongan kerja relevan sesuai minat dan keahlian\n• Melacak tahapan status lamaran secara real-time\n• Memperoleh notifikasi peluang karir yang sesuai profil").
        - FIELD FRUSTRATIONS: Tuliskan minimal 2 sampai 3 poin kendala/frustrasi konkret menggunakan bullet points (contoh: "• Proses melamar yang panjang dan harus mengisi form berulang kali\n• Minimnya transparansi feedback atau penolakan dari perusahaan\n• Algoritma pencarian yang menampilkan lowongan tidak relevan").

    2. EPICS (4 - 5 modul utama yang komprehensif)
        - Susun 4 sampai 5 Epic modul utama aplikasi yang mencakup siklus hidup sistem secara menyeluruh (contoh: Autentikasi & Akun, Pencarian & Rekomendasi, Manajemen Lamaran & Seleksi, Dashboard & Analitik Pengguna, serta Notifikasi & Komunikasi).
        - Deskripsi 2-3 kalimat yang menjelaskan cakupan bisnis dan batas kerja modul tersebut secara tegas.

    3. USER STORIES (LENGKAP & DETAIL: MINIMAL 2 - 3 story PER SETIAP EPIC, total 8 - 14 user stories)
        - PERHATIAN MUTLAK: SETIAP Epic yang kamu buat di poin (2) WAJIB MEMILIKI minimal 2 hingga 3 User Story di bawahnya! DILARANG KERAS ada Epic yang hanya memiliki 0 atau 1 user story!
        - WAJIB VARIASIKAN `user_type` di seluruh User Stories! Setiap User Type yang ada di poin (1) HARUS memiliki porsi User Story yang seimbang dan merepresentasikan peran nyata mereka (misal: ada cerita untuk Pelamar/Pencari Kerja, Perekrut/HRD, dan Administrator/Sistem).
        - Setiap story WAJIB mencakup skenario kerja nyata: alur utama (happy path), validasi input/kondisi khusus, dan aksi tindak lanjut.
        - Detail setiap story:
          * epic_name: nama Epic terkait (HARUS cocok persis dengan salah satu nama Epic di atas)
          * user_type: nama User Type terkait (HARUS cocok persis dengan salah satu nama User Type di atas)
          * story_name: judul fitur spesifik dan ringkas (contoh: 'Filter & Cari Lowongan Berdasarkan Gaji', 'Pasang Lowongan & Kriteria Kandidat', 'Verifikasi Dokumen Portofolio Pelamar', 'Export Laporan Rekrutmen Bulanan')
          * description: narasi lengkap & terstruktur minimal 3-4 kalimat: 'Sebagai [user_type], saya ingin [aksi/fitur spesifik], agar [tujuan & manfaat bisnis terukur].' Sertakan ringkasan alur interaksi pengguna dan umpan balik sistem.
          * acceptance_criteria: 2-3 kriteria penerimaan terukur dalam format Given-When-Then.
          * tech_notes: 2-3 catatan teknis arsitektur/API/database/keamanan.
          * test_cases: 2-3 skenario pengujian QA konkret (positif & edge case).

    4. NON-FUNCTIONAL REQUIREMENTS (WAJIB 4 - 5 NFR spesifik & terukur)
        - WAJIB buat 4 sampai 5 NFR konkret mencakup kategori: Performance, Security, Reliability, Usability, dan Data Privacy/Scalability.
        - Setiap NFR WAJIB memiliki target kuantitatif/terukur (contoh: 'Waktu respons API < 1.5 detik', 'Uptime 99.5%', 'Enkripsi data TLS 1.3 & password hashing bcrypt/Argon2', 'Kepatuhan UU PDP dalam penyimpanan data pribadi').
        - DILARANG membiarkan array NFR kosong!

    5. USER JOURNEY
        - WAJIB hasilkan objek `user_journey`:
          * narrative: 5-7 kalimat narasi komprehensif yang menceritakan perjalanan alur pengguna dari mulai membuka aplikasi/daftar hingga berhasil menyelesaikan tujuan utamanya.
          * steps: 5-7 tahapan langkah berurutan dari awal sampai akhir, dengan title, deskripsi aksi UI/respons sistem konkret, dan assign persona_name yang melakukan aksi tersebut.

    6. FORMAT
        - Gunakan Bahasa Indonesia yang baik dan profesional.
        - Jaga isi tetap berbobot, detail, bervariasi, tidak monoton, dan hasilkan output sesuai skema JSON.
    """

    try:
        output = _generate_structured(prompt, ProjectRequirementsOutput, temperature=0.3, max_tokens=4096)
    except Exception as e:
        raise RuntimeError(f"Gagal generate project requirements: {str(e)}") from e

    # Proteksi mutlak: pastikan nfrs selalu terisi minimal 4 kategori standar industri jika AI mengosongkannya
    if not output.nfrs or len(output.nfrs) < 2:
        output.nfrs = [
            NFRSuggestion(
                category="Performance",
                description=f"Waktu respons sistem untuk pemuatan data dan API utama {project_name} rata-rata di bawah 1.5 detik pada koneksi internet standar, mampu menangani hingga 500 permintaan bersamaan (concurrent requests) tanpa degradasi performa."
            ),
            NFRSuggestion(
                category="Security",
                description=f"Seluruh komunikasi data wajib menggunakan protokol HTTPS (TLS 1.3), kata sandi pengguna di-hash dengan algoritma aman (bcrypt/Argon2), serta otorisasi berbasis token JWT dengan pembatasan hak akses sesuai peran user."
            ),
            NFRSuggestion(
                category="Reliability",
                description=f"Tingkat ketersediaan layanan (uptime) sistem {project_name} ditargetkan minimal 99.5% per bulan, didukung mekanisme pencadangan (backup) basis data otomatis berkala dan toleransi pemulihan bencana (RTO) maksimal 2 jam."
            ),
            NFRSuggestion(
                category="Usability",
                description=f"Antarmuka pengguna dirancang responsif di berbagai perangkat (desktop, tablet, mobile), intuitif, dan memenuhi standar aksesibilitas WCAG 2.1 level AA dengan kurva belajar pengguna baru di bawah 15 menit."
            ),
        ]

    # Proteksi mutlak: pastikan SETIAP Epic memiliki minimal 2 user stories lengkap
    default_role = output.user_types[0].name if output.user_types else "Pengguna"
    for epic in output.epics:
        stories_in_epic = [s for s in output.user_stories if s.epic_name == epic.name]
        if len(stories_in_epic) < 2:
            needed = 2 - len(stories_in_epic)
            for k in range(needed):
                action_name = "Kelola & Pantau Alur" if k == 0 else "Konfigurasi & Validasi Data"
                output.user_stories.append(
                    UserStorySuggestion(
                        epic_name=epic.name,
                        story_name=f"{action_name} {epic.name}",
                        user_type=default_role,
                        description=(
                            f"Sebagai {default_role}, saya ingin menjalankan fitur {action_name.lower()} pada modul {epic.name}, "
                            f"agar seluruh proses dan alur kerja dapat tercatat dengan akurat dan efisien di sistem."
                        ),
                        acceptance_criteria=[
                            f"Given {default_role} membuka modul {epic.name}, When melakukan aksi {action_name.lower()}, Then sistem memproses dan menampilkan konfirmasi sukses.",
                            f"Given parameter input tidak valid atau koneksi bermasalah, When pengguna mengirim formulir, Then sistem menampilkan pesan validasi yang jelas."
                        ],
                        tech_notes=[
                            f"Endpoint API terproteksi JWT untuk aksi {action_name.lower()} pada modul {epic.name}",
                            "Validasi skema payload dan pencatatan audit log transaksi"
                        ],
                        test_cases=[
                            f"Uji pengiriman data valid pada {action_name.lower()} {epic.name} menghasilkan status 200/201",
                            "Uji skenario validasi gagal jika field wajib kosong menghasilkan status 422/400"
                        ]
                    )
                )

    # Proteksi mutlak: pastikan user_journey selalu memiliki narasi dan langkah konkret
    if not output.user_journey or not output.user_journey.narrative or not output.user_journey.steps:
        primary_persona = (
            output.user_types[0].personas[0].name
            if (output.user_types and output.user_types[0].personas)
            else (output.user_types[0].name if output.user_types else "Pengguna")
        )
        output.user_journey = UserJourneySuggestion(
            narrative=(
                f"Pengguna ({primary_persona}) membuka aplikasi {project_name} untuk memenuhi kebutuhan "
                f"utamanya secara efisien. Melalui tahapan onboarding, eksplorasi fitur pada modul utama, "
                f"hingga eksekusi tugas inti, sistem menyediakan antarmuka responsif dan alur yang jelas "
                f"sehingga tujuan tercapai tanpa hambatan teknis."
            ),
            steps=[
                UserJourneyStepSuggestion(
                    title="Membuka Aplikasi & Onboarding",
                    description=f"{primary_persona} mengakses halaman awal {project_name} dan melihat ikhtisar fitur serta alur onboarding yang ramah.",
                    persona_name=primary_persona
                ),
                UserJourneyStepSuggestion(
                    title="Autentikasi & Masuk Akun",
                    description=f"{primary_persona} melakukan proses autentikasi untuk memperoleh akses penuh ke fitur yang dipersonalisasi.",
                    persona_name=primary_persona
                ),
                UserJourneyStepSuggestion(
                    title="Eksplorasi Modul Utama",
                    description=f"{primary_persona} menavigasi menu modul utama aplikasi dan menemukan data atau tindakan yang relevan dengan kebutuhannya.",
                    persona_name=primary_persona
                ),
                UserJourneyStepSuggestion(
                    title="Eksekusi Aktivitas Inti",
                    description=f"{primary_persona} mengisi data atau menjalankan tindakan utama, dan sistem memberikan umpan balik validasi secara instan.",
                    persona_name=primary_persona
                ),
                UserJourneyStepSuggestion(
                    title="Konfirmasi & Penyelesaian Tujuan",
                    description=f"Sistem menampilkan status sukses dan konfirmasi akhir, menandai bahwa sasaran utama {primary_persona} telah berhasil diselesaikan.",
                    persona_name=primary_persona
                ),
            ]
        )

    return output

def suggest_project_description(project_name: str, platform_type: str) -> str:
    """Menghasilkan draf deskripsi proyek singkat (2-4 kalimat) berdasarkan nama & platform"""
    prompt = f"""
    Kamu adalah asisten business analyst berpengalaman.
    Buatkan draf deskripsi proyek software singkat (2-4 kalimat) berdasarkan detail berikut:

    - Nama proyek: {project_name}
    - Tipe platform: {platform_type}

    Deskripsi harus menjelaskan tujuan utama aplikasi, target penggunanya, dan gambaran fitur inti secara umum.
    Tulis dalam Bahasa Indonesia, gaya natural dan profesional, tanpa markdown, tanpa tanda kutip di awal/akhir.
    """.strip()

    try:
        description = _generate_text(prompt, temperature=0.6)
    except Exception as e:
        raise RuntimeError(f"Gagal memanggil AI: {str(e)}")

    if not description:
        raise ValueError("AI tidak menghasilkan deskripsi")

    return description

def suggest_user_type_description(project_name: str, user_type_name: str, project_description: str = "") -> str:
    """
    Menghasilkan draf deskripsi singkat (maksimal 6 kalimat) untuk SATU tipe pengguna,
    dipakai tombol AI Suggest (ikon Sparkles) di step UserTypes wizard.
    """
    context_line = (
        f"Deskripsi proyek: {project_description}"
        if project_description
        else "Tidak ada deskripsi proyek tambahan."
    )

    prompt = f"""
Kamu adalah business analyst berpengalaman yang membantu menyusun dokumentasi kebutuhan software.

Nama Proyek: {project_name}
{context_line}
Tipe Pengguna: {user_type_name}

Tugasmu: tuliskan deskripsi singkat dan padat (MAKSIMAL 3 kalimat, jangan lebih panjang) untuk
tipe pengguna "{user_type_name}" pada proyek "{project_name}" ini. Jelaskan: (1) siapa mereka,
(2) apa peran utama mereka di aplikasi ini, dan (3) tingkat akses mereka dibanding tipe pengguna
lain. Deskripsi harus kontekstual terhadap nama dan deskripsi proyek ini -- JANGAN kalimat
generik yang bisa berlaku untuk aplikasi apa saja.

Tulis dalam Bahasa Indonesia, gaya natural dan profesional, tanpa markdown, tanpa tanda kutip di
awal/akhir.
""".strip()

    try:
        description = _generate_text(prompt, temperature=0.5)
    except Exception as e:
        raise RuntimeError(f"Gagal memanggil AI: {str(e)}")

    if not description:
        raise ValueError("AI tidak menghasilkan deskripsi")

    return description

def suggest_user_goals(project_name: str, user_type_name: str, user_type_description: str) -> UserGoalsSuggestion:
    """Menghasilkan saran goals & frustrations untuk satu tipe pengguna, dipakai di step UserTypeGoals wizard"""
    context_line = (
        f"Deskripsi tipe pengguna ini: {user_type_description}"
        if user_type_description
        else "Tidak ada deskripsi tambahan untuk tipe pengguna ini."
    )

    prompt = f"""
Kamu adalah UX researcher berpengalaman yang membantu menyusun user persona untuk sebuah proyek software.

Nama Proyek: {project_name}
Tipe Pengguna: {user_type_name}
{context_line}

Tugasmu: tuliskan (1) goals — apa yang ingin dicapai tipe pengguna ini saat memakai aplikasi
"{project_name}", dan (2) frustrations — hal-hal yang membuat mereka frustrasi jika aplikasi
ini tidak memenuhi kebutuhan mereka. Keduanya harus spesifik terhadap peran "{user_type_name}"
dan konteks proyek ini, bukan kalimat generik yang bisa dipakai untuk aplikasi apa saja.

Tulis dalam Bahasa Indonesia, gaya natural dan profesional.
""".strip()

    try:
        return _generate_structured(prompt, UserGoalsSuggestion, temperature=0.4)
    except Exception as e:
        raise RuntimeError(f"Gagal memanggil AI: {str(e)}")


def suggest_user_journey(
    project_name: str,
    project_description: str,
    personas: List[dict],
) -> UserJourneySuggestion:
    """
    personas: list of {"name": str, "user_type": str, "about": str}
    Diambil dari semua Persona di project (lintas UserType), supaya AI bisa
    assign step ke persona yang benar-benar ada di project ini.
    """
    if personas:
        personas_lines = "\n".join(
            f"- {p['name']} (Tipe: {p.get('user_type', '-')})"
            f"{': ' + p['about'] if p.get('about') else ''}"
            for p in personas
        )
    else:
        personas_lines = "Tidak ada persona terdaftar."

    prompt = f"""
Kamu adalah UX researcher dan system analyst profesional. Buatlah draf user journey yang komprehensif, logis, dan detail untuk aplikasi ini dari awal (start) sampai selesai (end).

Nama Proyek: {project_name}
Deskripsi Proyek: {project_description or 'Tidak ada deskripsi.'}

DAFTAR PERSONA YANG TERLIBAT (WAJIB dipakai untuk assign persona_name di setiap step, JANGAN membuat nama baru di luar daftar ini):
{personas_lines}

ATURAN KETAT:
1. Setiap step WAJIB di-assign ke SATU persona dari daftar di atas yang paling relevan melakukan aksi tersebut. Field "persona_name" harus PERSIS SAMA (termasuk huruf besar/kecil) dengan salah satu nama persona di daftar -- jangan mengarang nama baru.
2. Journey boleh melibatkan lebih dari satu persona berbeda di step yang berbeda jika relevan dengan alur (misal: User submit request di step 2, lalu Admin approve di step 3).
3. Buat alur dari awal titik masuk (start) hingga mencapai tujuan akhir (end) secara runtut dan operasional.
4. Hasilkan dalam dua bentuk:
   (1) narrative: paragraf ringkasan alur secara utuh, profesional, dan operasional.
   (2) steps: 10 hingga 15 tahapan berurutan, tiap tahap punya title, description, dan persona_name.

Tulis dalam Bahasa Indonesia, gaya natural dan profesional.
""".strip()

    try:
        return _generate_structured(prompt, UserJourneySuggestion, temperature=0.4)
    except Exception as e:
        raise RuntimeError(f"Gagal memanggil AI: {str(e)}")


def suggest_tech_stack(project_name: str, project_description: str, application_type: str) -> TechStackSuggestion:
    """Menyarankan seluruh konfigurasi Technology Stack (Application Details, Development
    Approach, dan Architecture per-layer) berdasarkan konteks proyek."""
    prompt = f"""
Kamu adalah Solutions Architect berpengalaman. Berdasarkan detail proyek berikut, sarankan
konfigurasi technology stack yang paling sesuai, mencakup:
(1) perkiraan target pengguna & skala sistem,
(2) pendekatan/platform pengembangan (misalnya web-based dengan AI-assisted development),
(3) arsitektur 4 lapisan: User Interface (bahasa, framework, UI library), Application (bahasa,
    framework), Data (database), dan Integration (protokol).

Pilih teknologi yang umum, stabil, dan sesuai skala proyek ini -- bukan pilihan eksotis tanpa
alasan kuat.

Nama Proyek: {project_name}
Deskripsi: {project_description or 'Tidak ada deskripsi.'}
Tipe Aplikasi: {application_type or 'Tidak disebutkan'}

Tulis dalam Bahasa Indonesia untuk penjelasan jika ada, tapi nama teknologi tetap istilah asli
(contoh: "Next.js", "FastAPI", "PostgreSQL").
""".strip()

    try:
        return _generate_structured(prompt, TechStackSuggestion, temperature=0.3)
    except Exception as e:
        raise RuntimeError(f"Gagal memanggil AI: {str(e)}")

GUIDELINE_CATEGORY_LABELS = {
    "project_structure": "Project Structure",
    "security": "Security",
    "frontend": "Frontend Guidelines",
    "backend": "Backend Guidelines",
    "database": "Database Guidelines",
}

def suggest_guideline_by_category(project_name: str, tech_stack_summary: str, category_key: str) -> GuidelineSuggestion:
    """Menyarankan draf SATU coding guideline untuk satu kategori tetap (project_structure,
    security, frontend, backend, atau database), spesifik terhadap tech stack proyek."""
    label = GUIDELINE_CATEGORY_LABELS.get(category_key, category_key)
    prompt = f"""
Kamu adalah Tech Lead berpengalaman yang menyusun coding guidelines untuk tim developer baru.

Nama Proyek: {project_name}
Tech Stack: {tech_stack_summary or 'Belum ditentukan, gunakan asumsi stack modern yang umum untuk aplikasi web.'}
Kategori Guideline: {label}

Tuliskan SATU guideline lengkap khusus kategori "{label}" untuk proyek ini. Isi harus konkret,
actionable, dan spesifik terhadap tech stack di atas (dalam bentuk paragraf atau beberapa
poin singkat yang digabung jadi satu isi), bukan saran generik yang bisa berlaku untuk stack
apa saja.

Field "title" WAJIB persis: "{label}"

Tulis dalam Bahasa Indonesia.
""".strip()
    try:
        return _generate_structured(prompt, GuidelineSuggestion, temperature=0.3)
    except Exception as e:
        raise RuntimeError(f"Gagal generate guideline kategori {label}: {str(e)}") from e


def suggest_guideline_by_topic(project_name: str, tech_stack_summary: str, topic: str) -> GuidelineSuggestion:
    """Menyarankan draf coding guideline untuk topik custom / bebas (misal: 'Penamaan Variabel',
    'Unit Testing Standard', 'Error Handling Pattern')."""
    prompt = f"""
Kamu adalah Tech Lead berpengalaman yang menyusun coding guidelines untuk tim developer.

Nama Proyek: {project_name}
Tech Stack: {tech_stack_summary or 'Belum ditentukan, gunakan asumsi stack modern yang umum untuk aplikasi web.'}
Topik Guideline: {topic}

Tuliskan SATU guideline lengkap dan mendalam khusus mengenai topik "{topic}" untuk proyek ini. Isi harus konkret, actionable, dan spesifik terhadap tech stack di atas (dalam bentuk penjelasan best practice, aturan baku, atau poin-poin standar penulisan kode), bukan saran generik.

Field "title" WAJIB: "{topic}"

Tulis dalam Bahasa Indonesia.
""".strip()
    try:
        return _generate_structured(prompt, GuidelineSuggestion, temperature=0.3)
    except Exception as e:
        raise RuntimeError(f"Gagal generate guideline untuk topik {topic}: {str(e)}") from e


def suggest_coding_guidelines(project_name: str, tech_stack_summary: str) -> CodingGuidelinesSuggestion:
    """[LEGACY] Menyarankan draf coding guidelines bebas (5-7 item) berdasarkan tech stack.
    Dipertahankan untuk kompatibilitas, halaman Build sekarang memakai
    suggest_guideline_by_category untuk 5 kategori tetap."""
    prompt = f"""
Kamu adalah Tech Lead berpengalaman yang menyusun coding guidelines untuk tim developer baru.

Nama Proyek: {project_name}
Tech Stack: {tech_stack_summary}

Susun 5-7 coding guideline paling penting dan actionable untuk stack ini (contoh topik: struktur
folder, konvensi penamaan, penanganan error, testing, keamanan dasar) -- sesuaikan dengan
teknologi yang disebutkan, jangan generik.

Tulis dalam Bahasa Indonesia.
""".strip()

    try:
        return _generate_structured(prompt, CodingGuidelinesSuggestion, temperature=0.3)
    except Exception as e:
        raise RuntimeError(f"Gagal memanggil AI: {str(e)}")


def suggest_dev_plan(project_name: str, epic_names: List[str]) -> DevPlanSuggestion:
    """[LEGACY] Menyusun draf development plan ringkas (satu per Epic). Dipertahankan untuk
    kompatibilitas, halaman Build sekarang memakai suggest_dev_plan_for_epic yang lebih detail."""
    epics_line = ", ".join(epic_names) if epic_names else "Tidak ada epic yang terdaftar."

    prompt = f"""
Kamu adalah Project Manager teknis yang menyusun rencana pengembangan awal (development plan)
untuk sebuah proyek software, berdasarkan modul-modul (Epic) yang sudah didefinisikan.

Nama Proyek: {project_name}
Daftar Epic: {epics_line}

Buat satu task development untuk MASING-MASING epic di atas (jumlah task = jumlah epic),
diurutkan berdasarkan prioritas logis (fondasi seperti autentikasi/setup lebih dulu). Judul
task boleh mengikuti nama epic-nya, deskripsi singkat 3-4 kalimat cakupan kerjanya.

Tulis dalam Bahasa Indonesia.
""".strip()

    try:
        return _generate_structured(prompt, DevPlanSuggestion, temperature=0.3)
    except Exception as e:
        raise RuntimeError(f"Gagal memanggil AI: {str(e)}")


def suggest_dev_plan_for_epic(
    project_name: str,
    epic_name: str,
    epic_description: str,
    tech_stack_summary: str,
    guidelines_summary: str,
) -> DevPlanDetailSuggestion:
    """Menyusun SATU Development Plan detail untuk satu Epic/requirement, siap dipakai
    AI coding agent (Claude Code, Cursor, Lovable, v0, dsb) untuk implementasi langsung."""
    prompt = f"""
Kamu adalah Tech Lead/Project Manager teknis yang menyusun development plan detail untuk
dieksekusi oleh AI coding agent (Claude Code, Cursor, Lovable, v0, dsb).

Nama Proyek: {project_name}
Epic/Modul: {epic_name}
Deskripsi Epic: {epic_description or 'Tidak ada deskripsi tambahan.'}
Tech Stack Proyek: {tech_stack_summary or 'Belum ditentukan.'}
Coding Guidelines Proyek: {guidelines_summary or 'Belum ada guideline khusus, gunakan best practice umum.'}

Susun development plan yang detail dan siap dieksekusi langsung oleh AI coding agent tanpa
klarifikasi tambahan sesuai skema yang ditentukan.

Tulis dalam Bahasa Indonesia.
""".strip()
    try:
        return _generate_structured(prompt, DevPlanDetailSuggestion, temperature=0.3, max_tokens=4096)
    except Exception as e:
        raise RuntimeError(f"Gagal generate dev plan untuk epic {epic_name}: {str(e)}") from e

# ================= TAMBAHAN: REGENERATE / REFINE SINGLE USER STORY =================

class SingleStoryRegenerateSuggestion(BaseModel):
    as_a: str = Field(description="Role atau persona pengguna yang spesifik (misal: Pelanggan Terdaftar, Admin Finansial)")
    i_want: str = Field(description="Aksi atau fitur spesifik yang ingin dilakukan pengguna")
    so_that: str = Field(description="Manfaat atau nilai bisnis yang diperoleh dari fitur tersebut")
    acceptance_criteria: List[str] = Field(
        description="3-5 kriteria penerimaan spesifik dalam format: 'Given [kondisi], When [aksi], Then [hasil]'"
    )
    tech_notes: List[str] = Field(
        description="3-5 catatan teknis konkret untuk developer (struktur data, API endpoint, validasi, keamanan)"
    )
    test_cases: List[str] = Field(
        description="2-4 skenario pengujian untuk tim QA (contoh: 'Validasi form submit tanpa field wajib')"
    )

# ================= TAMBAHAN: SARAN LINKED STORIES (per-story) =================

class StoryLinkSuggestionItem(BaseModel):
    target_code: str = Field(
        description="Kode story tujuan yang berkaitan (HARUS persis sama dengan salah satu kode di daftar story lain yang diberikan)"
    )
    link_type: str = Field(
        description="Tipe hubungan: 'relates_to' jika sekadar berkaitan topik/fitur, atau 'blocked_by' jika story ini tidak bisa/tidak masuk akal dikerjakan sebelum story tujuan selesai"
    )


class StoryLinkSuggestionsOutput(BaseModel):
    links: List[StoryLinkSuggestionItem] = Field(
        description=(
            "Daftar link yang relevan dari story yang sedang dianalisis ke story lain. Kosongkan "
            "(array kosong) jika tidak ada hubungan yang jelas -- jangan memaksakan hubungan yang "
            "lemah atau terlalu umum."
        )
    )


def suggest_story_links(
    source_code: str,
    source_as_a: str,
    source_i_want: str,
    source_so_that: str,
    other_stories: List[dict],  # [{"code": str, "as_a": str, "i_want": str, "so_that": str}, ...]
) -> StoryLinkSuggestionsOutput:
    """Menganalisis satu story terhadap semua story lain dalam project yang sama, dan menyarankan
    link (relates_to / blocked_by) yang relevan. Dipakai tombol 'Generate with AI' di sidebar
    Stories Linked To pada ManualStoryDetailPanel."""
    if not other_stories:
        return StoryLinkSuggestionsOutput(links=[])

    others_lines = "\n".join(
        f"- {s['code']}: As a {s.get('as_a') or 'User'}, I want {s.get('i_want')}, so that {s.get('so_that') or '-'}"
        for s in other_stories
    )

    prompt = f"""
Kamu adalah Business Analyst yang menganalisis keterkaitan antar User Story dalam satu proyek software.

STORY YANG SEDANG DIANALISIS:
Kode: {source_code}
As a: {source_as_a or 'User'}
I want: {source_i_want}
So that: {source_so_that or '-'}

DAFTAR STORY LAIN DALAM PROYEK YANG SAMA:
{others_lines}

Tugasmu: identifikasi story lain di atas yang punya keterkaitan JELAS dengan story yang sedang
dianalisis. Untuk setiap keterkaitan yang kamu temukan, tentukan tipenya:
- "relates_to": story saling berkaitan topik/alur fitur, tapi TIDAK saling bergantung urutan pengerjaannya.
- "blocked_by": story yang sedang dianalisis TIDAK BISA/tidak masuk akal dikerjakan SEBELUM story
  tujuan selesai (ada dependency nyata, misal butuh data/state dari story lain terlebih dahulu).

Field target_code HARUS PERSIS SAMA dengan salah satu kode di daftar di atas. Jangan membuat
hubungan yang dipaksakan atau terlalu umum -- kalau memang tidak ada story yang benar-benar
berkaitan, kembalikan array kosong.
""".strip()

    try:
        return _generate_structured(prompt, StoryLinkSuggestionsOutput, temperature=0.3)
    except Exception as e:
        raise RuntimeError(f"Gagal generate saran story links: {str(e)}") from e
    
def suggest_story_refinement(
    as_a: str = "",
    i_want: str = "",
    so_that: str = "",
    epic_name: str = "",
    project_name: str = ""
) -> SingleStoryRegenerateSuggestion:
    """Menyempurnakan narasi User Story, Acceptance Criteria, Tech Notes, dan Test Cases menggunakan AI."""
    prompt = f"""
Kamu adalah Agile Product Owner & Technical Architect berpengalaman.
Tugasmu adalah menyempurnakan atau membuatkan User Story profesional yang lengkap.

Konteks Proyek: {project_name or 'Aplikasi Web/Mobile Modern'}
Modul/Epic Terkait: {epic_name or 'Umum'}

Draf User Story Saat Ini:
- As a: {as_a or 'Pengguna'}
- I want: {i_want or 'Melakukan sesuatu'}
- So that: {so_that or 'Mendapatkan kemudahan'}

Instruksi:
1. Sempurnakan 'as_a', 'i_want', dan 'so_that' agar profesional, spesifik, dan sesuai standar Agile.
2. Buatkan 3-5 Acceptance Criteria terukur dalam format 'Given..., When..., Then...'.
3. Buatkan 3-5 Tech Notes arsitektur/backend/database yang relevan.
4. Buatkan 2-4 Test Cases untuk QA.
5. Tuliskan seluruh output dalam Bahasa Indonesia.
""".strip()

    try:
        return _generate_structured(prompt, SingleStoryRegenerateSuggestion, temperature=0.3)
    except Exception as e:
        raise RuntimeError(f"Gagal generate User Story dengan AI: {str(e)}") from e