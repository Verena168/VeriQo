"""Who is in which team, and which application belongs to a person.

Since Stage 1, an application belongs to a TEAM (a solo entrant is a team of one). A person's
application in a hackathon is the application of the team in which they are a CONFIRMED member.
"""

import uuid

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Application, Team, TeamMember, User
from app.models.application import ApplicationStatus
from app.models.team import ACTIVE_MEMBER_STATUSES, MemberStatus


async def active_membership(db: AsyncSession, hackathon_id: uuid.UUID, user_id: uuid.UUID) -> TeamMember | None:
    """The person's live (invited or confirmed) membership in this hackathon, if any."""
    return await db.scalar(
        select(TeamMember).where(
            TeamMember.hackathon_id == hackathon_id, TeamMember.user_id == user_id,
            TeamMember.status.in_(ACTIVE_MEMBER_STATUSES),
        )
    )


async def confirmed_team_id(db: AsyncSession, hackathon_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID | None:
    return await db.scalar(
        select(TeamMember.team_id).where(
            TeamMember.hackathon_id == hackathon_id, TeamMember.user_id == user_id,
            TeamMember.status == MemberStatus.CONFIRMED,
        )
    )


async def application_for(db: AsyncSession, hackathon_id: uuid.UUID, user_id: uuid.UUID) -> Application | None:
    """The application of the team this person is a confirmed member of (None if not registered)."""
    team_id = await confirmed_team_id(db, hackathon_id, user_id)
    if team_id is None:
        return None
    return await db.scalar(select(Application).where(Application.team_id == team_id))


def member_has_published_shortlist(user_id, hackathon_id=None):
    """SQL condition: the person is a confirmed member of a team whose shortlisting is published.

    Use wherever access depends on being shortlisted (submissions, telemetry, extension list),
    so an unpublished decision can't be inferred from what suddenly works.
    """
    conds = [
        TeamMember.user_id == user_id,
        TeamMember.status == MemberStatus.CONFIRMED,
        Application.team_id == TeamMember.team_id,
        Application.status == ApplicationStatus.SHORTLISTED,
        Application.decision_published_at.is_not(None),
    ]
    if hackathon_id is not None:
        conds.append(TeamMember.hackathon_id == hackathon_id)
    return exists().where(and_(*conds))


async def confirmed_members(db: AsyncSession, team_id: uuid.UUID) -> list[User]:
    rows = await db.scalars(
        select(User).join(TeamMember, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team_id, TeamMember.status == MemberStatus.CONFIRMED)
        .order_by(TeamMember.is_lead.desc(), TeamMember.joined_at)
    )
    return list(rows)


async def load_team(db: AsyncSession, team_id: uuid.UUID) -> Team | None:
    return await db.scalar(
        select(Team).where(Team.id == team_id).options(
            selectinload(Team.members).selectinload(TeamMember.user),
            selectinload(Team.artifacts),
            selectinload(Team.application),
        ).execution_options(populate_existing=True)
    )
