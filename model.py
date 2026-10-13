from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    last_login = Column(DateTime, nullable=True)

    workspaces_owned = relationship("Workspace", back_populates="owner")
    workspace_memberships = relationship("WorkspaceMember", back_populates="user")
    projects_created = relationship("Project", back_populates="creator")

class VerificationOTP(Base):
    __tablename__ = "verification_otps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    otp_code = Column(String, nullable=False)
    purpose = Column(String, nullable=False, default="change_password")
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_used = Column(Boolean, default=False)

    user = relationship("User")

class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="workspaces_owned")
    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="workspace", cascade="all, delete-orphan")
    ai_rules = relationship("AIRule", back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String, default="viewer")
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="workspace_memberships")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    application_type = Column(String, nullable=True)
    domain_business = Column(String, nullable=True)
    target_users = Column(String, nullable=True)
    business_goals = Column(String, nullable=True)
    repo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    workspace = relationship("Workspace", back_populates="projects")
    creator = relationship("User", back_populates="projects_created")
    ai_rules = relationship("AIRule", back_populates="project", cascade="all, delete-orphan")
    user_types = relationship("UserType", back_populates="project", cascade="all, delete-orphan")
    epics = relationship("Epic", back_populates="project", cascade="all, delete-orphan")
    nfrs = relationship("NFR", back_populates="project", cascade="all, delete-orphan")
    user_journeys = relationship("UserJourney", back_populates="project", cascade="all, delete-orphan")

    # PERBAIKAN: cascade="all, delete-orphan" agar tech_stack ikut terhapus otomatis
    tech_stack = relationship("TechStack", back_populates="project", uselist=False, cascade="all, delete-orphan")

    coding_guidelines = relationship("CodingGuideline", back_populates="project", cascade="all, delete-orphan")
    development_plans = relationship("DevelopmentPlan", back_populates="project", cascade="all, delete-orphan")

class AIRule(Base):
    __tablename__ = "ai_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)

    project = relationship("Project", back_populates="ai_rules")
    workspace = relationship("Workspace", back_populates="ai_rules")

class UserType(Base):
    __tablename__ = "user_types"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    project = relationship("Project", back_populates="user_types")
    personas = relationship("Persona", back_populates="user_type", cascade="all, delete-orphan")
    stories = relationship("UserStory", back_populates="user_type")

class Persona(Base):
    __tablename__ = "personas"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    location = Column(String, nullable=True)
    family_status = Column(String, nullable=True)
    job_title = Column(String, nullable=True)
    about = Column(String, nullable=True)
    goals = Column(String, nullable=True)
    frustrations = Column(String, nullable=True)
    user_type_id = Column(Integer, ForeignKey("user_types.id"), nullable=False)
    user_type = relationship("UserType", back_populates="personas")
    journey_steps = relationship("JourneyStep", back_populates="persona")

class Epic(Base):
    __tablename__ = "epics"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    project = relationship("Project", back_populates="epics")
    stories = relationship("UserStory", back_populates="epic", cascade="all, delete-orphan")
    # TAMBAHAN: relasi ke DevelopmentPlan, dipakai untuk menghubungkan
    # satu Dev Plan ke Epic/requirement asalnya.
    dev_plans = relationship("DevelopmentPlan", back_populates="epic")

class UserStory(Base):
    __tablename__ = "user_stories"
    id = Column(Integer, primary_key=True, index=True)
    epic_id = Column(Integer, ForeignKey("epics.id"), nullable=False)
    user_type_id = Column(Integer, ForeignKey("user_types.id"), nullable=True)
    code = Column(String, nullable=True)
    as_a = Column(String, nullable=True)
    i_want = Column(String, nullable=False)
    so_that = Column(String, nullable=True)
    status = Column(String, default="draft")
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    epic = relationship("Epic", back_populates="stories")
    user_type = relationship("UserType", back_populates="stories")
    acceptance_criteria = relationship("AcceptanceCriteria", back_populates="user_story", cascade="all, delete-orphan")
    tech_notes = relationship("TechNote", back_populates="user_story", cascade="all, delete-orphan")
    test_cases = relationship("TestCase", back_populates="user_story", cascade="all, delete-orphan")
    images = relationship("StoryImage", back_populates="user_story", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="user_story", cascade="all, delete-orphan")
    labels = Column(String, nullable=True)  # JSON-encoded list, e.g. '["Frontend","MVP"]'
    links_from = relationship("StoryLink", foreign_keys="StoryLink.source_story_id", back_populates="source_story", cascade="all, delete-orphan")
    links_to = relationship("StoryLink", foreign_keys="StoryLink.target_story_id", back_populates="target_story", cascade="all, delete-orphan")
    journey_links = relationship("JourneyStoryLink", back_populates="story", cascade="all, delete-orphan")
    
class AcceptanceCriteria(Base):
    __tablename__ = "acceptance_criteria"
    id = Column(Integer, primary_key=True, index=True)
    user_story_id = Column(Integer, ForeignKey("user_stories.id"), nullable=False)
    description = Column(String, nullable=False)
    user_story = relationship("UserStory", back_populates="acceptance_criteria")

class TechNote(Base):
    __tablename__ = "tech_notes"
    id = Column(Integer, primary_key=True, index=True)
    user_story_id = Column(Integer, ForeignKey("user_stories.id"), nullable=False)
    content = Column(String, nullable=False)
    user_story = relationship("UserStory", back_populates="tech_notes")

class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    user_story_id = Column(Integer, ForeignKey("user_stories.id"), nullable=False)
    action = Column(Text, nullable=False, default="")
    expected_result = Column(Text, nullable=False, default="")

    user_story = relationship("UserStory", back_populates="test_cases")

class StoryImage(Base):
    __tablename__ = "story_images"

    id = Column(Integer, primary_key=True, index=True)
    user_story_id = Column(Integer, ForeignKey("user_stories.id"), nullable=False)
    url = Column(String, nullable=False)
    caption = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user_story = relationship("UserStory", back_populates="images")

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    user_story_id = Column(Integer, ForeignKey("user_stories.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user_story = relationship("UserStory", back_populates="comments")
    user = relationship("User")

class StoryLink(Base):
    __tablename__ = "story_links"

    id = Column(Integer, primary_key=True, index=True)
    source_story_id = Column(Integer, ForeignKey("user_stories.id"), nullable=False)
    target_story_id = Column(Integer, ForeignKey("user_stories.id"), nullable=False)
    link_type = Column(String, nullable=False)  # "relates_to" | "blocked_by"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    source_story = relationship("UserStory", foreign_keys=[source_story_id], back_populates="links_from")
    target_story = relationship("UserStory", foreign_keys=[target_story_id], back_populates="links_to")
    
class NFR(Base):
    __tablename__ = "nfrs"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)
    description = Column(String, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    project = relationship("Project", back_populates="nfrs")

class UserJourney(Base):
    __tablename__ = "user_journeys"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    project = relationship("Project", back_populates="user_journeys")
    steps = relationship("JourneyStep", back_populates="user_journey", cascade="all, delete-orphan")

class JourneyStep(Base):
    __tablename__ = "journey_steps"
    id = Column(Integer, primary_key=True, index=True)
    user_journey_id = Column(Integer, ForeignKey("user_journeys.id"), nullable=False)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True)
    step_order = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    user_journey = relationship("UserJourney", back_populates="steps")
    persona = relationship("Persona", back_populates="journey_steps")
    story_links = relationship("JourneyStoryLink", back_populates="journey_step", cascade="all, delete-orphan")

class JourneyStoryLink(Base):
    __tablename__ = "journey_story_links"

    id = Column(Integer, primary_key=True, index=True)
    journey_step_id = Column(Integer, ForeignKey("journey_steps.id", ondelete="CASCADE"), nullable=False)
    story_id = Column(Integer, ForeignKey("user_stories.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    journey_step = relationship("JourneyStep", back_populates="story_links")
    story = relationship("UserStory", back_populates="journey_links")

    __table_args__ = (
        UniqueConstraint("journey_step_id", "story_id", name="uq_journey_step_story"),
    )

# ===== FR007: BUILD MODULE =====
# PERBAIKAN BESAR: TechStack, CodingGuideline, dan DevelopmentPlan diperluas supaya
# datanya cocok dengan tampilan Build page yang baru (Technology Stack Configuration,
# 5 kategori Coding Guidelines tetap, dan Dev Plans dengan status draft/todo/in_progress/completed).

class TechStack(Base):
    __tablename__ = "tech_stacks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # --- Application Details ---
    target_users = Column(String, nullable=True)      # Contoh: "1.000 - 10.000 pengguna aktif"
    scale = Column(String, nullable=True)              # Contoh: "Small to Medium Scale"

    # --- Development Approach ---
    platform = Column(String, nullable=True)           # Contoh: "Web-based, AI-assisted development"

    # --- Architecture: User Interface Layer ---
    ui_language = Column(String, nullable=True)        # Contoh: TypeScript
    ui_framework = Column(String, nullable=True)       # Contoh: Next.js
    ui_library = Column(String, nullable=True)         # Contoh: Tailwind CSS, shadcn/ui

    # --- Architecture: Application Layer ---
    app_language = Column(String, nullable=True)       # Contoh: Python
    app_framework = Column(String, nullable=True)      # Contoh: FastAPI

    # --- Architecture: Data Layer ---
    data_layer = Column(String, nullable=True)         # Contoh: PostgreSQL (nama database)

    # --- Architecture: Integration Layer ---
    integration_layer = Column(String, nullable=True)  # Contoh: REST API

    # Kolom lama, dipertahankan agar backward-compatible dengan data lama (tidak dipakai UI baru)
    ui_layer = Column(String, nullable=True)
    app_layer = Column(String, nullable=True)

    # ===== TAMBAHAN: hasil wizard "Translate" (reverse engineer existing software) =====
    additional_technologies = Column(String, nullable=True)  # JSON-encoded list, e.g. '["React","PostgreSQL"]'
    lines_of_code = Column(String, nullable=True)             # diisi kalau user tahu jumlah baris kode
    years_in_development = Column(String, nullable=True)      # diisi kalau user gak tahu lines_of_code
    size_class = Column(String, nullable=True)                # small | medium | large
    code_structure = Column(String, nullable=True)            # modular | monolithic | legacy
    has_db_logic = Column(String, nullable=True)               # "yes" | "no"
    uses_microservices = Column(String, nullable=True)         # "yes" | "no"
    complexity_notes = Column(String, nullable=True)           # jawaban textarea "other complexity"

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project = relationship("Project", back_populates="tech_stack")

class CodingGuideline(Base):
    __tablename__ = "coding_guidelines"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    # category = salah satu dari project_structure | security | frontend | backend | database.
    # None berarti guideline custom yang ditambahkan manual lewat "Add new Coding Guideline".
    category = Column(String, nullable=True)
    title = Column(String, nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project = relationship("Project", back_populates="coding_guidelines")


class DevelopmentPlan(Base):
    __tablename__ = "development_plans"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    # TAMBAHAN: link opsional ke Epic/requirement asal plan ini dibuat
    epic_id = Column(Integer, ForeignKey("epics.id"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="draft")  # draft | todo | in_progress | completed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project = relationship("Project", back_populates="development_plans")
    epic = relationship("Epic", back_populates="dev_plans")


# ===== TOKEN USAGE TRACKING =====

class AiTokenUsage(Base):
    __tablename__ = "ai_token_usages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    provider = Column(String, nullable=False)        # gemini | openrouter | groq
    model_name = Column(String, nullable=False)      # gemini-2.0-flash | dll
    feature = Column(String, nullable=False)         # requirements_generation | user_journey | dll
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")
    workspace = relationship("Workspace")
    project = relationship("Project")