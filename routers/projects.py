import re
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List
from services.ai import (
    ProjectRequirementsOutput,
    generate_project_requirements,
    suggest_project_description,
    suggest_user_goals,
    suggest_user_journey,
    suggest_user_type_description,
    suggest_nfr_draft,
    suggest_nfr_refinement,
    suggest_epic_draft,
    suggest_epic_refinement,
    suggest_user_type_draft,
)
import model
import schemas
import auth
from database import get_db
from services.token_tracker import record_token_usage
from services.pdf_generator import build_project_pdf

router = APIRouter(prefix="/api/projects", tags=["Projects"])


def check_workspace_access(workspace_id: int, user_id: int, db: Session, required_roles: List[str] = None):
    """Helper untuk memverifikasi apakah user adalah anggota workspace dengan role tertentu"""
    membership = db.query(model.WorkspaceMember).filter(
        model.WorkspaceMember.workspace_id == workspace_id,
        model.WorkspaceMember.user_id == user_id
    ).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Anda tidak memiliki akses ke ruang kerja ini"
        )

    if required_roles and membership.role not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tindakan ini memerlukan peran: {', '.join(required_roles)}"
        )

    return membership


@router.post("", response_model=schemas.ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    project_data: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Membuat proyek baru di dalam workspace (Hanya Owner dan Editor yang diizinkan)"""
    check_workspace_access(
        workspace_id=project_data.workspace_id,
        user_id=current_user.id,
        db=db,
        required_roles=["owner", "editor"]
    )

    new_project = model.Project(
        name=project_data.name,
        description=project_data.description,
        application_type=project_data.application_type,
        domain_business=project_data.domain_business,
        target_users=project_data.target_users,
        business_goals=project_data.business_goals,
        repo_url=project_data.repo_url,
        workspace_id=project_data.workspace_id,
        creator_id=current_user.id
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project


@router.get("", response_model=List[schemas.ProjectResponse])
def get_projects(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Mendapatkan seluruh proyek dalam suatu workspace (Semua anggota workspace bisa akses)"""
    check_workspace_access(workspace_id=workspace_id, user_id=current_user.id, db=db)
    projects = db.query(model.Project).filter(model.Project.workspace_id == workspace_id).all()
    return projects


@router.get("/{id}", response_model=schemas.ProjectResponse)
def get_project_by_id(
    id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Mendapatkan detail dari sebuah proyek"""
    project = db.query(model.Project).filter(model.Project.id == id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyek tidak ditemukan")

    check_workspace_access(workspace_id=project.workspace_id, user_id=current_user.id, db=db)
    return project


@router.put("/{id}", response_model=schemas.ProjectResponse)
def update_project(
    id: int,
    project_data: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Mengubah info proyek (Hanya Owner dan Editor yang diizinkan)"""
    project = db.query(model.Project).filter(model.Project.id == id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyek tidak ditemukan")

    check_workspace_access(
        workspace_id=project.workspace_id,
        user_id=current_user.id,
        db=db,
        required_roles=["owner", "editor"]
    )

    update_data = project_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Menghapus project beserta relasi turunannya secara aman (Hanya Owner dan Editor yang diizinkan)"""
    project = db.query(model.Project).filter(model.Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project tidak ditemukan"
        )

    # FIX: sebelumnya endpoint ini TIDAK memverifikasi bahwa current_user adalah
    # anggota workspace project ini (apalagi punya role owner/editor). Artinya
    # SIAPA SAJA yang login bisa menghapus project MANAPUN cuma dengan menebak
    # project_id (IDOR). Sekarang wajib melalui check_workspace_access dulu,
    # konsisten dengan update_project di atas.
    check_workspace_access(
        workspace_id=project.workspace_id,
        user_id=current_user.id,
        db=db,
        required_roles=["owner", "editor"]
    )

    # Catatan: model.TechStack, model.UserType, model.Epic, model.NFR,
    # model.UserJourney, model.AIRule, model.CodingGuideline, dan
    # model.DevelopmentPlan semuanya sudah didefinisikan dengan
    # cascade="all, delete-orphan" pada relasi Project, jadi baris delete
    # manual untuk TechStack di bawah ini sebenarnya redundant -- tapi
    # dibiarkan (tidak berbahaya) untuk menjaga kompatibilitas dengan
    # kemungkinan data lama yang belum konsisten relasinya.
    db.query(model.TechStack).filter(model.TechStack.project_id == project_id).delete()

    db.delete(project)
    db.commit()

    return {"message": "Project berhasil dihapus"}

@router.post("/suggest-description", response_model=schemas.SuggestDescriptionResponse)
def suggest_description(
    payload: schemas.SuggestDescriptionRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    """Memanggil AI untuk memberikan draf deskripsi proyek singkat, dipakai di step DescribeProject wizard"""
    try:
        description = suggest_project_description(
            project_name=payload.project_name,
            platform_type=payload.platform_type
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI gagal memberikan saran deskripsi: {str(e)}"
        )

    return schemas.SuggestDescriptionResponse(description=description)

@router.post("/suggest-user-goals", response_model=schemas.SuggestUserGoalsResponse)
def suggest_user_goals_endpoint(
    payload: schemas.SuggestUserGoalsRequest,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Memanggil AI untuk memberikan saran goals & frustrations untuk satu tipe pengguna"""
    try:
        result = suggest_user_goals(
            project_name=payload.project_name,
            user_type_name=payload.user_type_name,
            user_type_description=payload.user_type_description or ""
        )

        prompt_text = f"{payload.project_name} {payload.user_type_name} {payload.user_type_description or ''}"
        response_text = f"{result.goals} {result.frustrations}"
        record_token_usage(
            db=db,
            user_id=current_user.id,
            provider="gemini",
            model_name="gemini-2.0-flash",
            feature="Persona Generation",
            prompt_text=prompt_text,
            response_text=response_text
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI gagal memberikan saran goals & frustrations: {str(e)}"
        )

    return schemas.SuggestUserGoalsResponse(goals=result.goals, frustrations=result.frustrations)


@router.post("/suggest-user-journey", response_model=schemas.SuggestUserJourneyResponse)
def suggest_user_journey_endpoint(
    payload: schemas.SuggestUserJourneyRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    """Memanggil AI untuk memberikan draf narasi DAN langkah-langkah user journey terstruktur"""
    persona_payload = [
        {"name": p.name, "user_type": p.user_type or "-", "about": p.about or ""}
        for p in payload.personas
    ]

    try:
        result = suggest_user_journey(
            project_name=payload.project_name,
            project_description=payload.project_description or "",
            personas=persona_payload,   # <- ganti dari user_types=payload.user_types
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI gagal memberikan saran user journey: {str(e)}"
        )

    return schemas.SuggestUserJourneyResponse(
        journey=result.narrative,
        steps=[
            schemas.SuggestUserJourneyStepItem(
                title=s.title,
                description=s.description,
                persona_name=s.persona_name,   # <- BARU
            )
            for s in result.steps
        ]
    )

@router.post("/{id}/generate-requirements")
def generate_requirements(
    id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Memanggil Gemini AI untuk menghasilkan draf kebutuhan proyek secara otomatis"""
    project = db.query(model.Project).filter(model.Project.id == id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyek tidak ditemukan")

    check_workspace_access(
        workspace_id=project.workspace_id,
        user_id=current_user.id,
        db=db,
        required_roles=["owner", "editor"]
    )

    project_rules = db.query(model.AIRule).filter(model.AIRule.project_id == id).all()
    workspace_rules = db.query(model.AIRule).filter(
        model.AIRule.workspace_id == project.workspace_id,
        model.AIRule.project_id == None
    ).all()

    all_rules_text = [rule.content for rule in project_rules] + [rule.content for rule in workspace_rules]

    try:
        requirements_draft = generate_project_requirements(
            project_name=project.name,
            project_description=project.description or "",
            application_type=project.application_type or "",
            domain_business=project.domain_business or "",
            target_users=project.target_users or "",
            business_goals=project.business_goals or "",
            ai_rules=all_rules_text
        )
        return requirements_draft

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI gagal memproses data: {str(e)}"
        )


@router.post("/{id}/save-requirements", status_code=status.HTTP_201_CREATED)
def save_project_requirements(
    id: int,
    requirements: schemas.SaveRequirementsPayload,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Menyimpan draf kebutuhan proyek (User Types, Epics, Stories + AC + Tech Notes +
    Test Cases, NFRs) hasil generate AI ke database"""
    project = db.query(model.Project).filter(model.Project.id == id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyek tidak ditemukan")

    check_workspace_access(
        workspace_id=project.workspace_id,
        user_id=current_user.id,
        db=db,
        required_roles=["owner", "editor"]
    )

    # 1. Simpan User Types + Personas
    user_type_map = {}
    for ut_data in requirements.user_types:
        db_ut = model.UserType(
            name=ut_data.name,
            description=ut_data.description,
            project_id=id
        )
        db.add(db_ut)
        db.commit()
        db.refresh(db_ut)
        user_type_map[ut_data.name] = db_ut.id

        # TAMBAHAN: sebelumnya personas hasil AI generate tidak pernah disimpan sama
        # sekali (AI bahkan belum diminta menghasilkannya) — sekarang disimpan di sini.
        for persona_data in getattr(ut_data, "personas", []) or []:
            db_persona = model.Persona(
                name=persona_data.name,
                age=persona_data.age,
                location=persona_data.location,
                family_status=persona_data.family_status,
                job_title=persona_data.job_title,
                about=persona_data.about,
                goals=persona_data.goals,
                frustrations=persona_data.frustrations,
                user_type_id=db_ut.id
            )
            db.add(db_persona)
        db.commit()

    # 2. Simpan Epics
    epic_map = {}
    for epic_data in requirements.epics:
        db_epic = model.Epic(
            name=epic_data.name,
            description=epic_data.description,
            project_id=id
        )
        db.add(db_epic)
        db.commit()
        db.refresh(db_epic)
        epic_map[epic_data.name] = db_epic.id

    # 3. Simpan User Stories + Acceptance Criteria + Tech Notes + Test Cases
    for story_data in requirements.user_stories:
        epic_id = epic_map.get(story_data.epic_name)
        user_type_id = user_type_map.get(story_data.user_type)

        db_story = model.UserStory(
            epic_id=epic_id,
            user_type_id=user_type_id,
            as_a=story_data.user_type,
            i_want=story_data.story_name,
            so_that=story_data.description,
            status="draft",
            project_id=id
        )
        db.add(db_story)
        db.commit()
        db.refresh(db_story)

        for ac_desc in story_data.acceptance_criteria:
            db_ac = model.AcceptanceCriteria(
                user_story_id=db_story.id,
                description=ac_desc
            )
            db.add(db_ac)

        # TAMBAHAN: simpan tech notes
        for note in story_data.tech_notes:
            db_note = model.TechNote(
                user_story_id=db_story.id,
                content=note
            )
            db.add(db_note)

        # TAMBAHAN: simpan test cases
        for tc in story_data.test_cases:
            db_tc = model.TestCase(
                user_story_id=db_story.id,
                description=tc
            )
            db.add(db_tc)

    # 4. Simpan NFRs
    for nfr_data in requirements.nfrs:
        db_nfr = model.NFR(
            category=nfr_data.category,
            description=nfr_data.description,
            project_id=id
        )
        db.add(db_nfr)

    db.commit()
    return {"message": "Draf kebutuhan proyek berhasil disimpan ke database"}

@router.post("/suggest-user-type-description", response_model=schemas.SuggestUserTypeDescriptionResponse)
def suggest_user_type_description_endpoint(
    payload: schemas.SuggestUserTypeDescriptionRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    """Memanggil AI untuk memberikan draf deskripsi singkat untuk satu tipe pengguna"""
    try:
        description = suggest_user_type_description(
            project_name=payload.project_name,
            user_type_name=payload.user_type_name,
            project_description=payload.project_description or ""
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI gagal memberikan saran deskripsi tipe pengguna: {str(e)}"
        )

    return schemas.SuggestUserTypeDescriptionResponse(description=description)

@router.post("/suggest-user-type-draft", response_model=schemas.SuggestUserTypeDraftResponse)
def suggest_user_type_draft_endpoint(
    payload: schemas.SuggestUserTypeDraftRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    """AI Draft: menyarankan satu user type baru (name + description) yang belum ada di daftar."""
    try:
        result = suggest_user_type_draft(
            project_name=payload.project_name,
            project_description=payload.project_description or "",
            application_type=payload.application_type or "",
            domain_business=payload.domain_business or "",
            existing_user_types=payload.existing_user_types,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI gagal membuat draf tipe pengguna: {str(e)}"
        )

    return schemas.SuggestUserTypeDraftResponse(name=result.name, description=result.description)

@router.post("/suggest-nfr-draft", response_model=schemas.SuggestNFRDraftResponse)
def suggest_nfr_draft_endpoint(
    payload: schemas.SuggestNFRDraftRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    """AI Draft: menyarankan satu NFR baru (kategori + deskripsi) yang belum ada di daftar."""
    try:
        result = suggest_nfr_draft(
            project_name=payload.project_name,
            project_description=payload.project_description or "",
            application_type=payload.application_type or "",
            domain_business=payload.domain_business or "",
            existing_categories=payload.existing_categories,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI gagal membuat draf NFR: {str(e)}"
        )

    return schemas.SuggestNFRDraftResponse(category=result.category, description=result.description)

@router.post("/suggest-nfr-refine", response_model=schemas.SuggestNFRRefineResponse)
def suggest_nfr_refine_endpoint(
    payload: schemas.SuggestNFRRefineRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    """AI Suggest: menyempurnakan NFR yang sudah ada (dipakai saat mode edit)."""
    try:
        result = suggest_nfr_refinement(
            category=payload.category,
            description=payload.description or "",
            project_name=payload.project_name or "",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI gagal menyempurnakan NFR: {str(e)}"
        )

    return schemas.SuggestNFRRefineResponse(category=result.category, description=result.description)

@router.post("/suggest-epic-draft", response_model=schemas.SuggestEpicDraftResponse)
def suggest_epic_draft_endpoint(
    payload: schemas.SuggestEpicDraftRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    """AI Draft: menyarankan satu epic baru (title + description) yang belum ada di daftar."""
    try:
        result = suggest_epic_draft(
            project_name=payload.project_name,
            project_description=payload.project_description or "",
            application_type=payload.application_type or "",
            domain_business=payload.domain_business or "",
            existing_epics=payload.existing_epics,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI gagal membuat draf epic: {str(e)}"
        )

    return schemas.SuggestEpicDraftResponse(title=result.title, description=result.description)


@router.post("/suggest-epic-refine", response_model=schemas.SuggestEpicRefineResponse)
def suggest_epic_refine_endpoint(
    payload: schemas.SuggestEpicRefineRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    """AI Suggest: menyempurnakan epic yang sudah ada (dipakai saat mode edit)."""
    try:
        result = suggest_epic_refinement(
            title=payload.title,
            description=payload.description or "",
            project_name=payload.project_name or "",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI gagal menyempurnakan epic: {str(e)}"
        )

    return schemas.SuggestEpicRefineResponse(title=result.title, description=result.description)


@router.get("/{project_id}/export/pdf")
def export_project_pdf(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user),
):
    """Mengekspor seluruh spesifikasi kebutuhan proyek ke dalam bentuk dokumen PDF (PRD/SRS)."""
    project = db.query(model.Project).filter(model.Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyek tidak ditemukan"
        )
    check_workspace_access(project.workspace_id, current_user.id, db)

    try:
        pdf_bytes = build_project_pdf(project)
        safe_filename = re.sub(r'[^a-zA-Z0-9_\-]', '_', project.name).strip('_') or 'project'
        headers = {
            "Content-Disposition": f'attachment; filename="{safe_filename}-spec.pdf"',
            "Content-Type": "application/pdf",
        }
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal membuat file PDF: {str(e)}"
        )