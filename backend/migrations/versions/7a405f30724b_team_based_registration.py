"""team-based registration

Applications move from one-per-person to one-per-team (docs/STAGE1_DESIGN.md §2.5, §2.8).

Data migration, in order:
  1. Existing (organizer-formed) teams become submitted, AI-formed teams. Their earliest member
     becomes lead; every member is confirmed. Their members' personal applications merge into one
     team application (lead's decision, average score, latest publish time).
  2. Applicants with no team get a solo team (a team of one) owning their application.
  3. Each person's CV moves to team_member_artifacts; team-less submissions join the solo team.
Old columns are dropped only after the data has been copied.

Revision ID: 7a405f30724b
Revises: 8a2858fdcb42
Create Date: 2026-11-01
"""
import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7a405f30724b"
down_revision: str | Sequence[str] | None = "8a2858fdcb42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEAM_STATUS = ("draft", "submitted", "withdrawn", "merged")


def _as_json(value):
    """JSONB may come back as text or as already-decoded Python data, depending on the driver."""
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)
MEMBER_STATUS = ("invited", "confirmed", "declined", "removed")


def upgrade() -> None:
    bind = op.get_bind()
    sa.Enum(*TEAM_STATUS, name="team_status").create(bind, checkfirst=True)
    sa.Enum(*MEMBER_STATUS, name="member_status").create(bind, checkfirst=True)

    # ---- 1. new columns / tables (nullable or defaulted, so existing rows stay valid)
    op.add_column("teams", sa.Column("lead_user_id", sa.UUID(), nullable=True))
    op.add_column("teams", sa.Column("status", sa.Enum(*TEAM_STATUS, name="team_status", create_type=False),
                                     server_default="draft", nullable=False))
    op.add_column("teams", sa.Column("formed_by", sa.String(length=10), server_default="self", nullable=False))
    op.add_column("teams", sa.Column("seeking_teammates", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("teams", sa.Column("merged_into_id", sa.UUID(), nullable=True))
    op.add_column("teams", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("teams_lead_user_id_fkey", "teams", "users", ["lead_user_id"], ["id"])
    op.create_foreign_key("teams_merged_into_id_fkey", "teams", "teams", ["merged_into_id"], ["id"])

    op.add_column("team_members", sa.Column("is_lead", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("team_members", sa.Column("status", sa.Enum(*MEMBER_STATUS, name="member_status", create_type=False),
                                            server_default="confirmed", nullable=False))
    op.add_column("team_members", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "team_member_artifacts",
        sa.Column("team_id", sa.UUID(), sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("cv_file_id", sa.String(length=24), nullable=True),
        sa.Column("cv_filename", sa.String(length=255), nullable=True),
        sa.Column("github_url", sa.String(length=255), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("parse_status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("parse_note", sa.String(length=500), nullable=True),
        sa.Column("parsed_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("applications", sa.Column("team_id", sa.UUID(), nullable=True))
    op.add_column("applications", sa.Column("submitted_by", sa.UUID(), nullable=True))
    op.alter_column("applications", "user_id", nullable=True)  # new team rows have no single user; dropped below

    # ---- 2. data
    q = lambda sql, **kw: bind.execute(sa.text(sql), kw)  # noqa: E731

    def add_artifact(team_id, app_row):
        q("""INSERT INTO team_member_artifacts (team_id, user_id, cv_file_id, cv_filename, github_url, uploaded_by,
                 parse_status, parse_note, parsed_profile)
             SELECT :team, u.id, :cv, :fname, u.github_url, u.id, :pstatus, :note, u.parsed_skills
             FROM users u WHERE u.id = :uid""",
          team=team_id, uid=app_row.user_id, cv=app_row.cv_file_id, fname=app_row.resume_filename,
          pstatus="ok" if app_row.score is not None else "unreadable", note=app_row.review_note)

    # 2a. existing organizer-formed teams -> submitted AI teams with one merged application
    for team in q("SELECT id, hackathon_id, created_at FROM teams").all():
        members = q("SELECT user_id, joined_at FROM team_members WHERE team_id = :t ORDER BY joined_at, user_id",
                    t=team.id).all()
        if not members:
            continue
        lead = members[0].user_id
        q("""UPDATE teams SET lead_user_id = :lead, status = 'submitted', formed_by = 'ai', submitted_at = created_at
             WHERE id = :t""", lead=lead, t=team.id)
        q("UPDATE team_members SET status = 'confirmed', confirmed_at = joined_at, is_lead = (user_id = :lead) WHERE team_id = :t",
          lead=lead, t=team.id)
        apps = q("""SELECT * FROM applications WHERE hackathon_id = :h AND user_id IN
                    (SELECT user_id FROM team_members WHERE team_id = :t)""", h=team.hackathon_id, t=team.id).all()
        if not apps:
            continue
        lead_app = next((a for a in apps if a.user_id == lead), apps[0])
        scores = [a.score for a in apps if a.score is not None]
        published = [a.decision_published_at for a in apps if a.decision_published_at is not None]
        q("""INSERT INTO applications (id, team_id, submitted_by, hackathon_id, status, score, match_details,
                 pitch_deck_file_id, review_note, decision_published_at, applied_at)
             VALUES (:id, :t, :lead, :h, CAST(:status AS application_status), :score, CAST(:details AS jsonb),
                 :deck, NULL, :pub, :applied)""",
          id=uuid.uuid4(), t=team.id, lead=lead, h=team.hackathon_id, status=lead_app.status,
          score=sum(scores) / len(scores) if scores else None,
          details=_as_json(lead_app.match_details),
          deck=lead_app.pitch_deck_file_id, pub=max(published) if published else None,
          applied=min(a.applied_at for a in apps))
        for a in apps:
            add_artifact(team.id, a)
            q("DELETE FROM applications WHERE id = :id", id=a.id)

    # 2b. applicants with no team -> a solo team that owns their application
    for a in q("SELECT a.*, u.name AS user_name FROM applications a JOIN users u ON u.id = a.user_id WHERE a.team_id IS NULL").all():
        name, n = a.user_name, 2
        while q("SELECT 1 FROM teams WHERE hackathon_id = :h AND team_name = :n", h=a.hackathon_id, n=name).first():
            name, n = f"{a.user_name} ({n})", n + 1
        team_id = uuid.uuid4()
        q("""INSERT INTO teams (id, hackathon_id, team_name, lead_user_id, status, formed_by, submitted_at, created_at)
             VALUES (:id, :h, :name, :u, 'submitted', 'self', :at, :at)""",
          id=team_id, h=a.hackathon_id, name=name, u=a.user_id, at=a.applied_at)
        q("""INSERT INTO team_members (team_id, user_id, hackathon_id, is_lead, status, joined_at, confirmed_at, ai_recommended)
             VALUES (:t, :u, :h, true, 'confirmed', :at, :at, false)""", t=team_id, u=a.user_id, h=a.hackathon_id, at=a.applied_at)
        add_artifact(team_id, a)
        q("UPDATE applications SET team_id = :t, submitted_by = user_id WHERE id = :id", t=team_id, id=a.id)
        q("UPDATE submissions SET team_id = :t WHERE team_id IS NULL AND hackathon_id = :h AND user_id = :u",
          t=team_id, h=a.hackathon_id, u=a.user_id)

    # ---- 3. constraints and removal of per-person columns
    op.alter_column("applications", "team_id", nullable=False)
    op.alter_column("applications", "submitted_by", nullable=False)
    op.drop_constraint("applications_user_id_hackathon_id_key", "applications", type_="unique")
    op.drop_constraint("applications_user_id_fkey", "applications", type_="foreignkey")
    op.drop_column("applications", "user_id")
    op.drop_column("applications", "resume_filename")
    op.drop_column("applications", "cv_file_id")
    op.create_unique_constraint("applications_hackathon_id_team_id_key", "applications", ["hackathon_id", "team_id"])
    op.create_foreign_key("applications_team_id_fkey", "applications", "teams", ["team_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("applications_submitted_by_fkey", "applications", "users", ["submitted_by"], ["id"])

    op.drop_constraint("team_members_hackathon_id_user_id_key", "team_members", type_="unique")
    op.create_index("uq_team_members_active", "team_members", ["hackathon_id", "user_id"], unique=True,
                    postgresql_where=sa.text("status IN ('invited', 'confirmed')"))


def downgrade() -> None:
    """Back to one application per person: each confirmed member gets a copy of their team's application."""
    bind = op.get_bind()
    q = lambda sql, **kw: bind.execute(sa.text(sql), kw)  # noqa: E731

    op.add_column("applications", sa.Column("user_id", sa.UUID(), nullable=True))
    op.add_column("applications", sa.Column("resume_filename", sa.String(length=255), nullable=True))
    op.add_column("applications", sa.Column("cv_file_id", sa.String(length=24), nullable=True))
    op.drop_constraint("applications_hackathon_id_team_id_key", "applications", type_="unique")

    for app in q("SELECT * FROM applications").all():
        members = q("""SELECT m.user_id, x.cv_file_id, x.cv_filename FROM team_members m
                       LEFT JOIN team_member_artifacts x ON x.team_id = m.team_id AND x.user_id = m.user_id
                       WHERE m.team_id = :t AND m.status = 'confirmed'""", t=app.team_id).all()
        for i, m in enumerate(members):
            if i == 0:
                q("UPDATE applications SET user_id = :u, cv_file_id = :cv, resume_filename = :f WHERE id = :id",
                  u=m.user_id, cv=m.cv_file_id, f=m.cv_filename, id=app.id)
            else:
                q("""INSERT INTO applications (id, user_id, hackathon_id, team_id, submitted_by, status, score, match_details,
                         cv_file_id, resume_filename, pitch_deck_file_id, review_note, decision_published_at, applied_at)
                     SELECT :id, :u, hackathon_id, team_id, submitted_by, status, score, match_details, :cv, :f,
                         pitch_deck_file_id, review_note, decision_published_at, applied_at FROM applications WHERE id = :src""",
                  id=uuid.uuid4(), u=m.user_id, cv=m.cv_file_id, f=m.cv_filename, src=app.id)
    q("DELETE FROM applications WHERE user_id IS NULL")
    q("DELETE FROM team_members WHERE status <> 'confirmed'")

    op.drop_constraint("applications_team_id_fkey", "applications", type_="foreignkey")
    op.drop_constraint("applications_submitted_by_fkey", "applications", type_="foreignkey")
    op.drop_column("applications", "team_id")
    op.drop_column("applications", "submitted_by")
    op.alter_column("applications", "user_id", nullable=False)
    op.create_foreign_key("applications_user_id_fkey", "applications", "users", ["user_id"], ["id"])
    op.create_unique_constraint("applications_user_id_hackathon_id_key", "applications", ["user_id", "hackathon_id"])

    op.drop_index("uq_team_members_active", table_name="team_members", postgresql_where=sa.text("status IN ('invited', 'confirmed')"))
    op.create_unique_constraint("team_members_hackathon_id_user_id_key", "team_members", ["hackathon_id", "user_id"])
    op.drop_table("team_member_artifacts")
    op.drop_column("team_members", "confirmed_at")
    op.drop_column("team_members", "status")
    op.drop_column("team_members", "is_lead")
    op.drop_constraint("teams_merged_into_id_fkey", "teams", type_="foreignkey")
    op.drop_constraint("teams_lead_user_id_fkey", "teams", type_="foreignkey")
    for col in ("submitted_at", "merged_into_id", "seeking_teammates", "formed_by", "status", "lead_user_id"):
        op.drop_column("teams", col)
    sa.Enum(name="member_status").drop(bind, checkfirst=True)
    sa.Enum(name="team_status").drop(bind, checkfirst=True)
