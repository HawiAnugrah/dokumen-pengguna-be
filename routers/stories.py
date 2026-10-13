from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from services.ai import suggest_story_refinement, suggest_epic_draft, suggest_nfr_draft, suggest_story_links
import json
import model
import schemas
import auth
from database import get_db
import os
import shutil
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form

router = APIRouter(prefix="/api/stories", tags=["Epics & User Stories"])
UPLOAD_DIR = "static/story_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("/epics", response_model=List[schemas.EpicResponse])
def get_epics(project_id: int, db: Session = Depends(get_db), current_user: model.User = Depends(auth.get_current_user)):
    return db.query(model.Epic).filter(model.Epic.project_id == project_id).all()

@router.post("/epics", response_model=schemas.EpicResponse, status_code=status.HTTP_201_CREATED)
def create_epic(data: schemas.EpicCreate, db: Session = Depends(get_db), current_user: model.User = Depends(auth.get_current_user)):
    db_epic = model.Epic(name=data.name, description=data.description, project_id=data.project_id)
    db.add(db_epic)
    db.commit()
    db.refresh(db_epic)
    return db_epic

@router.put("/epics/{id}", response_model=schemas.EpicResponse)
def update_epic(
    id: int,
    data: schemas.EpicUpdate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    db_epic = db.query(model.Epic).filter(model.Epic.id == id).first()
    if not db_epic:
        raise HTTPException(status_code=404, detail="Epic tidak ditemukan")

    if data.name is not None:
        trimmed = data.name.strip()
        if not trimmed:
            raise HTTPException(status_code=400, detail="Nama epic tidak boleh kosong")
        db_epic.name = trimmed
    if data.description is not None:
        db_epic.description = data.description.strip() or None

    db.commit()
    db.refresh(db_epic)
    return db_epic

@router.get("", response_model=List[schemas.UserStoryResponse])
def get_stories(project_id: int, db: Session = Depends(get_db), current_user: model.User = Depends(auth.get_current_user)):
    return db.query(model.UserStory).filter(model.UserStory.project_id == project_id).all()

@router.post("", response_model=schemas.UserStoryResponse, status_code=status.HTTP_201_CREATED)
def create_story(data: schemas.UserStoryCreate, db: Session = Depends(get_db), current_user: model.User = Depends(auth.get_current_user)):
    db_story = model.UserStory(**data.model_dump())
    db.add(db_story)
    db.commit()
    db.refresh(db_story)
    return db_story

@router.put("/{id}", response_model=schemas.UserStoryResponse)
def update_story(
    id: int, 
    data: schemas.UserStoryUpdate, 
    db: Session = Depends(get_db), 
    current_user: model.User = Depends(auth.get_current_user)
):
    db_story = db.query(model.UserStory).filter(model.UserStory.id == id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="User Story tidak ditemukan")

    if data.as_a is not None:
        db_story.as_a = data.as_a
    if data.i_want is not None:
        db_story.i_want = data.i_want
    if data.so_that is not None:
        db_story.so_that = data.so_that
    if data.status is not None:
        db_story.status = data.status
    if data.code is not None:
        db_story.code = data.code

    # Sinkronisasi Acceptance Criteria ke tabel database
    if data.acceptance_criteria is not None:
        db.query(model.AcceptanceCriteria).filter(model.AcceptanceCriteria.user_story_id == id).delete()
        for ac_desc in data.acceptance_criteria:
            if ac_desc and str(ac_desc).strip():
                db.add(model.AcceptanceCriteria(user_story_id=id, description=str(ac_desc).strip()))

    # Sinkronisasi Tech Notes ke tabel database
    if data.tech_notes is not None:
        db.query(model.TechNote).filter(model.TechNote.user_story_id == id).delete()
        for note_content in data.tech_notes:
            if note_content and str(note_content).strip():
                db.add(model.TechNote(user_story_id=id, content=str(note_content).strip()))

    # Sinkronisasi Test Cases ke tabel database
    if data.test_cases is not None:
        db.query(model.TestCase).filter(model.TestCase.user_story_id == id).delete()
        for tc in data.test_cases:
            if tc:
                db.add(model.TestCase(
                    user_story_id=id,
                    action=tc.action if hasattr(tc, 'action') else getattr(tc, 'description', str(tc)),
                    expected_result=tc.expected_result if hasattr(tc, 'expected_result') else "",
                ))
    if data.labels is not None:
        db_story.labels = json.dumps(data.labels)
                
    db.commit()
    db.refresh(db_story)
    return db_story

@router.delete("/{id}")
def delete_story(id: int, db: Session = Depends(get_db), current_user: model.User = Depends(auth.get_current_user)):
    db_story = db.query(model.UserStory).filter(model.UserStory.id == id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="User Story tidak ditemukan")
    db.delete(db_story)
    db.commit()
    return {"message": "User story berhasil dihapus"}

# ================= TAMBAHAN: SEED EXAMPLE STORY (AiChoice -> "No, not at this stage") =================
@router.post("/seed-example", status_code=status.HTTP_201_CREATED)
def seed_example_story(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """
    Membuat 1 Epic + 1 User Story contoh (lengkap dengan Acceptance Criteria)
    untuk project yang baru dibuat, supaya dashboard Stories tidak kosong total
    saat user memilih 'No, not at this stage' di step AiChoice.

    Idempotent: kalau project ini sudah punya epic (misal user klik lagi atau
    reload), tidak akan bikin duplikat -- langsung return tanpa insert baru.
    """
    existing_epic = db.query(model.Epic).filter(model.Epic.project_id == project_id).first()
    if existing_epic:
        return {"message": "Project sudah memiliki data, seed dilewati.", "epic_id": existing_epic.id}

    db_epic = model.Epic(
        name="Getting Started",
        description="Contoh Epic bawaan untuk membantu kamu memahami struktur Userdoc.",
        project_id=project_id,
    )
    db.add(db_epic)
    db.commit()
    db.refresh(db_epic)

    db_story = model.UserStory(
        epic_id=db_epic.id,
        code="US-1.1",
        as_a="Customer",
        i_want="to create my first user story",
        so_that="I can describe the requirements of my system in a language everyone can understand",
        status="draft",
        project_id=project_id,
    )
    db.add(db_story)
    db.commit()
    db.refresh(db_story)

    example_criteria = [
        'Use acceptance criteria to capture what needs to happen for this story to be "done"',
        "It should be clear and concise",
        "Able to be understood by everyone",
        "Focus on the user's perspective",
        "Testable, meaning it can be used for defining, implementing, and testing a story",
        "You can link to other user stories by typing hash '#' and then the name of the story",
        "This helps you build a navigable map of your system",
        "You can also add resource links to each story in the 'Resources' panel on the right hand",
        "You can add images to your stories for better visualization of requirements or design mockups",
        "Images can be referenced directly within your descriptions and acceptance criteria",
        "This helps stakeholders understand the visual aspects of requirements",
    ]

    for desc in example_criteria:
        db.add(model.AcceptanceCriteria(user_story_id=db_story.id, description=desc))

    db.commit()

    return {"message": "Example story berhasil dibuat.", "epic_id": db_epic.id, "story_id": db_story.id}


# ================= TAMBAHAN: BATCH SAVE DARI WIZARD =================
@router.post("/batch", status_code=status.HTTP_201_CREATED)
def save_wizard_stories_batch(
    project_id: int, 
    data: schemas.WizardBatchCreateSchema, 
    db: Session = Depends(get_db), 
    current_user: model.User = Depends(auth.get_current_user)
):
    """Menyimpan seluruh Epics dan User Stories hasil wizard frontend secara sekaligus"""

    for epic_data in data.epics:
        db_epic = model.Epic(
            name=epic_data.name,
            description=epic_data.description,
            project_id=project_id
        )
        db.add(db_epic)
        db.commit()
        db.refresh(db_epic)

        # Simpan stories yang terikat ke epic ini.
        # model.UserStory TIDAK punya field storyName/userType/description —
        # field itu perlu di-mapping ke i_want / as_a / so_that.
        for story_data in epic_data.stories:
            # Cari UserType yang namanya cocok di project ini (kalau ada),
            # supaya story bisa terhubung ke user_type_id yang benar.
            user_type = db.query(model.UserType).filter(
                model.UserType.project_id == project_id,
                model.UserType.name == story_data.userType
            ).first()

            db_story = model.UserStory(
                epic_id=db_epic.id,
                user_type_id=user_type.id if user_type else None,
                as_a=story_data.userType,
                i_want=story_data.storyName,
                so_that=story_data.description,
                status="draft",
                project_id=project_id
            )
            db.add(db_story)

    db.commit()
    return {"message": "Semua data wizard berhasil disimpan ke database!"}

# ================= TAMBAHAN: ENDPOINT AI REGENERATE USER STORY =================
@router.post("/ai-suggest", response_model=schemas.StoryAiSuggestResponse)
def ai_suggest_user_story(
    data: schemas.StoryAiSuggestRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    """Menyempurnakan dan men-generate kelengkapan User Story menggunakan AI"""
    try:
        suggestion = suggest_story_refinement(
            as_a=data.as_a or "",
            i_want=data.i_want or "",
            so_that=data.so_that or "",
            epic_name=data.epic_name or "",
            project_name=data.project_name or ""
        )
        return schemas.StoryAiSuggestResponse(
            as_a=suggestion.as_a,
            i_want=suggestion.i_want,
            so_that=suggestion.so_that,
            acceptance_criteria=suggestion.acceptance_criteria,
            tech_notes=suggestion.tech_notes,
            test_cases=suggestion.test_cases
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================= NON-FUNCTIONAL REQUIREMENTS (NFR) =================

@router.get("/nfrs", response_model=List[schemas.NFRResponse])
def get_nfrs(project_id: int, db: Session = Depends(get_db), current_user: model.User = Depends(auth.get_current_user)):
    return db.query(model.NFR).filter(model.NFR.project_id == project_id).all()

@router.post("/nfrs", response_model=schemas.NFRResponse, status_code=status.HTTP_201_CREATED)
def create_nfr(data: schemas.NFRCreate, db: Session = Depends(get_db), current_user: model.User = Depends(auth.get_current_user)):
    db_nfr = model.NFR(category=data.category, description=data.description, project_id=data.project_id)
    db.add(db_nfr)
    db.commit()
    db.refresh(db_nfr)
    return db_nfr

@router.put("/nfrs/{id}", response_model=schemas.NFRResponse)
def update_nfr(
    id: int,
    data: schemas.NFRCreate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    db_nfr = db.query(model.NFR).filter(model.NFR.id == id).first()
    if not db_nfr:
        raise HTTPException(status_code=404, detail="NFR tidak ditemukan")
    db_nfr.category = data.category
    db_nfr.description = data.description
    db.commit()
    db.refresh(db_nfr)
    return db_nfr

@router.delete("/nfrs/{id}")
def delete_nfr(id: int, db: Session = Depends(get_db), current_user: model.User = Depends(auth.get_current_user)):
    db_nfr = db.query(model.NFR).filter(model.NFR.id == id).first()
    if not db_nfr:
        raise HTTPException(status_code=404, detail="NFR tidak ditemukan")
    db.delete(db_nfr)
    db.commit()
    return {"message": "NFR berhasil dihapus"}


# ================= AI-SUGGEST: EPIC & NFR =================

@router.post("/epics/ai-suggest", response_model=schemas.SuggestEpicDraftResponse)
def ai_suggest_epic(
    data: schemas.SuggestEpicDraftRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    try:
        suggestion = suggest_epic_draft(
            project_name=data.project_name,
            project_description=data.project_description or "",
            application_type=data.application_type or "",
            domain_business=data.domain_business or "",
            existing_epics=data.existing_epics,
        )
        return schemas.SuggestEpicDraftResponse(title=suggestion.title, description=suggestion.description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/nfrs/ai-suggest", response_model=schemas.SuggestNFRDraftResponse)
def ai_suggest_nfr(
    data: schemas.SuggestNFRDraftRequest,
    current_user: model.User = Depends(auth.get_current_user)
):
    try:
        suggestion = suggest_nfr_draft(
            project_name=data.project_name,
            project_description=data.project_description or "",
            application_type=data.application_type or "",
            domain_business=data.domain_business or "",
            existing_categories=data.existing_categories,
        )
        return schemas.SuggestNFRDraftResponse(category=suggestion.category, description=suggestion.description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ================= TAMBAHAN: STORY IMAGES / WIREFRAMES =================

@router.post("/{id}/images/upload", response_model=schemas.StoryImageResponse, status_code=status.HTTP_201_CREATED)
def upload_story_image(
    id: int,
    file: UploadFile = File(...),
    caption: str = Form(None),
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Upload file gambar untuk sebuah User Story (ke Supabase Cloud Storage atau fallback lokal)."""
    db_story = db.query(model.UserStory).filter(model.UserStory.id == id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="User Story tidak ditemukan")

    ext = os.path.splitext(file.filename or "")[1] or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    content_type = file.content_type or "image/png"
    file_bytes = file.file.read()

    from services.storage import upload_story_image as upload_story_image_file
    image_url = upload_story_image_file(file_bytes, filename, content_type=content_type)

    db_image = model.StoryImage(user_story_id=id, url=image_url, caption=caption)
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    return db_image


@router.post("/{id}/images", response_model=schemas.StoryImageResponse, status_code=status.HTTP_201_CREATED)
def add_story_image_url(
    id: int,
    data: schemas.StoryImageCreate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Tambah gambar via URL eksternal (bukan upload file)."""
    db_story = db.query(model.UserStory).filter(model.UserStory.id == id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="User Story tidak ditemukan")

    db_image = model.StoryImage(user_story_id=id, url=data.url, caption=data.caption)
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    return db_image


@router.delete("/images/{image_id}")
def delete_story_image(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    db_image = db.query(model.StoryImage).filter(model.StoryImage.id == image_id).first()
    if not db_image:
        raise HTTPException(status_code=404, detail="Gambar tidak ditemukan")

    # Hapus file fisik dari disk kalau itu file upload lokal (bukan URL eksternal)
    if db_image.url.startswith("/static/"):
        filepath = db_image.url.lstrip("/")
        if os.path.exists(filepath):
            os.remove(filepath)

    db.delete(db_image)
    db.commit()
    return {"message": "Gambar berhasil dihapus"}

# ================= TAMBAHAN: COMMENTS & DISKUSI TIM =================

@router.get("/{id}/comments", response_model=List[schemas.CommentResponse])
def get_story_comments(
    id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    db_story = db.query(model.UserStory).filter(model.UserStory.id == id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="User Story tidak ditemukan")

    return (
        db.query(model.Comment)
        .filter(model.Comment.user_story_id == id)
        .order_by(model.Comment.created_at.asc())
        .all()
    )


@router.post("/{id}/comments", response_model=schemas.CommentResponse, status_code=status.HTTP_201_CREATED)
def create_story_comment(
    id: int,
    data: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    db_story = db.query(model.UserStory).filter(model.UserStory.id == id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="User Story tidak ditemukan")

    if not data.content.strip():
        raise HTTPException(status_code=400, detail="Komentar tidak boleh kosong")

    db_comment = model.Comment(
        user_story_id=id,
        user_id=current_user.id,
        content=data.content.strip(),
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment

# ================= TAMBAHAN: LABELS & LINKED STORIES =================

@router.get("/{id}/links", response_model=schemas.StoryLinksResponse)
def get_story_links(
    id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    db_story = db.query(model.UserStory).filter(model.UserStory.id == id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="User Story tidak ditemukan")

    links_from = db.query(model.StoryLink).filter(model.StoryLink.source_story_id == id).all()
    links_to = db.query(model.StoryLink).filter(model.StoryLink.target_story_id == id).all()

    linked_to = [
        schemas.LinkedStoryItem(
            link_id=l.id,
            story_id=l.target_story.id,
            code=l.target_story.code,
            i_want=l.target_story.i_want,
            link_type=l.link_type,
        )
        for l in links_from
    ]
    linked_from = [
        schemas.LinkedStoryItem(
            link_id=l.id,
            story_id=l.source_story.id,
            code=l.source_story.code,
            i_want=l.source_story.i_want,
            link_type=l.link_type,
        )
        for l in links_to
    ]
    return schemas.StoryLinksResponse(linked_to=linked_to, linked_from=linked_from)


@router.post("/{id}/links", response_model=schemas.LinkedStoryItem, status_code=status.HTTP_201_CREATED)
def create_story_link(
    id: int,
    data: schemas.StoryLinkCreate,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    if data.target_story_id == id:
        raise HTTPException(status_code=400, detail="Story tidak bisa di-link ke dirinya sendiri")

    if data.link_type not in ("relates_to", "blocked_by"):
        raise HTTPException(status_code=400, detail="link_type harus 'relates_to' atau 'blocked_by'")

    db_story = db.query(model.UserStory).filter(model.UserStory.id == id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="User Story tidak ditemukan")

    target_story = db.query(model.UserStory).filter(model.UserStory.id == data.target_story_id).first()
    if not target_story:
        raise HTTPException(status_code=404, detail="Target story tidak ditemukan")

    db_link = model.StoryLink(
        source_story_id=id,
        target_story_id=data.target_story_id,
        link_type=data.link_type,
    )
    db.add(db_link)
    db.commit()
    db.refresh(db_link)

    return schemas.LinkedStoryItem(
        link_id=db_link.id,
        story_id=target_story.id,
        code=target_story.code,
        i_want=target_story.i_want,
        link_type=db_link.link_type,
    )


@router.delete("/links/{link_id}")
def delete_story_link(
    link_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    db_link = db.query(model.StoryLink).filter(model.StoryLink.id == link_id).first()
    if not db_link:
        raise HTTPException(status_code=404, detail="Link tidak ditemukan")

    db.delete(db_link)
    db.commit()
    return {"message": "Link berhasil dihapus"}

# ================= TAMBAHAN: GENERATE LINKS DENGAN AI =================

@router.post("/{id}/links/generate", response_model=schemas.StoryLinksResponse)
def generate_story_links_ai(
    id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    db_story = db.query(model.UserStory).filter(model.UserStory.id == id).first()
    if not db_story:
        raise HTTPException(status_code=404, detail="User Story tidak ditemukan")

    other_stories = db.query(model.UserStory).filter(
        model.UserStory.project_id == db_story.project_id,
        model.UserStory.id != id,
    ).all()

    if not other_stories:
        raise HTTPException(status_code=400, detail="Tidak ada story lain dalam project ini untuk di-link")

    def story_code(s):
        return s.code or f"US-{s.id}"

    others_payload = [
        {"code": story_code(s), "as_a": s.as_a, "i_want": s.i_want, "so_that": s.so_that}
        for s in other_stories
    ]

    try:
        suggestion = suggest_story_links(
            source_code=story_code(db_story),
            source_as_a=db_story.as_a,
            source_i_want=db_story.i_want,
            source_so_that=db_story.so_that,
            other_stories=others_payload,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    code_to_story = {story_code(s): s for s in other_stories}

    for item in suggestion.links:
        target = code_to_story.get(item.target_code)
        if not target or item.link_type not in ("relates_to", "blocked_by"):
            continue

        exists = db.query(model.StoryLink).filter(
            model.StoryLink.source_story_id == id,
            model.StoryLink.target_story_id == target.id,
            model.StoryLink.link_type == item.link_type,
        ).first()
        if exists:
            continue

        db.add(model.StoryLink(
            source_story_id=id,
            target_story_id=target.id,
            link_type=item.link_type,
        ))

    db.commit()

    links_from = db.query(model.StoryLink).filter(model.StoryLink.source_story_id == id).all()
    links_to = db.query(model.StoryLink).filter(model.StoryLink.target_story_id == id).all()

    linked_to = [
        schemas.LinkedStoryItem(
            link_id=l.id, story_id=l.target_story.id, code=l.target_story.code,
            i_want=l.target_story.i_want, link_type=l.link_type,
        ) for l in links_from
    ]
    linked_from = [
        schemas.LinkedStoryItem(
            link_id=l.id, story_id=l.source_story.id, code=l.source_story.code,
            i_want=l.source_story.i_want, link_type=l.link_type,
        ) for l in links_to
    ]
    return schemas.StoryLinksResponse(linked_to=linked_to, linked_from=linked_from)

@router.get("/{story_id}/journeys", response_model=List[schemas.JourneyLinkedFromResponse])
def get_journeys_linked_from_story(
    story_id: int,
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    links = (
        db.query(model.JourneyStoryLink)
        .join(model.JourneyStep)
        .filter(model.JourneyStoryLink.story_id == story_id)
        .all()
    )

    return [
        schemas.JourneyLinkedFromResponse(
            journey_id=link.journey_step.user_journey.id,
            journey_title=link.journey_step.user_journey.name,
            step_id=link.journey_step.id,
            step_title=link.journey_step.title,
        )
        for link in links
    ]