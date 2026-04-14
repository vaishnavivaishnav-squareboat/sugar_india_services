"""
app/api/routes/outreach.py
─────────────────────────────────────────────────────────────────────────────
All /outreach/* endpoints for the HORECA Lead Intelligence API.
─────────────────────────────────────────────────────────────────────────────
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import desc, select, not_, exists
from sqlalchemy.orm import aliased

from app.db.session import AsyncSessionLocal, celery_session
from app.db.orm import Lead, Contact, OutreachEmail
from app.utils import model_to_dict
from app.utils.smtp import send_email
from app.services.openai_client import client as openai_client
from app.core.config import OPENAI_MODEL
from app.core.constants import LeadStatus, EmailStatus, EmailType
from app.prompts.lead_email_api import lead_email_api_prompt
from app.prompts.follow_up_email import follow_up_email_prompt

outreach_router = APIRouter(prefix="/outreach")


@outreach_router.get("/emails")
async def get_all_emails(limit: int = 50):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OutreachEmail).order_by(desc(OutreachEmail.generated_at)).limit(limit)
        )
        return [model_to_dict(e) for e in result.scalars()]


@outreach_router.get("/{lead_id}/emails")
async def get_lead_emails(lead_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OutreachEmail)
            .where(OutreachEmail.lead_id == lead_id)
            .order_by(desc(OutreachEmail.generated_at))
            .limit(20)
        )
        return [model_to_dict(e) for e in result.scalars()]


@outreach_router.put("/{email_id}/mark-sent")
async def mark_email_sent(email_id: str):
    async with AsyncSessionLocal() as session:
        email = (await session.execute(
            select(OutreachEmail).where(OutreachEmail.id == email_id)
        )).scalar_one_or_none()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")

        if email.status == EmailStatus.SENT:
            raise HTTPException(status_code=400, detail="Email has already been sent")

        # Resolve the recipient — prefer stored sent_to_email, else look up contact
        to_email = email.sent_to_email or ""
        if not to_email:
            contact = (await session.execute(
                select(Contact)
                .where(Contact.lead_id == email.lead_id)
                .order_by(Contact.is_primary.desc())
                .limit(1)
            )).scalar_one_or_none()
            if not contact or not contact.email:
                raise HTTPException(
                    status_code=422,
                    detail="No email address found for this lead's contact. Add a contact email first.",
                )
            to_email = contact.email

        # Send via SMTP (dummy or real — toggled in app/utils/smtp.py)
        try:
            await send_email(to_email, email.subject, email.body, lead_id=email.lead_id)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Email delivery failed: {exc}")

        # Persist sent status
        email.status        = EmailStatus.SENT
        email.sent_at       = datetime.now(timezone.utc)
        email.sent_to_email = to_email

        await session.commit()
        await session.refresh(email)
        return model_to_dict(email)


# ─── helpers ─────────────────────────────────────────────────────────────────

async def _generate_email_content(lead: dict, primary_contact) -> tuple[str, str]:
    """Return (subject, body) for a lead using OpenAI."""
    dm         = (primary_contact.name if primary_contact else None) or "Procurement Manager"
    first_name = dm.split()[0] if dm else "Sir/Madam"

    prompt = lead_email_api_prompt(
        business_name           = lead["business_name"],
        segment                 = lead["segment"],
        city                    = lead["city"],
        dm                      = dm,
        first_name              = first_name,
        role                    = (primary_contact.role if primary_contact else None) or "F&B Head",
        rating                  = lead["rating"],
        num_outlets             = lead["num_outlets"],
        has_dessert_menu        = lead["has_dessert_menu"],
        monthly_volume_estimate = lead.get("monthly_volume_estimate") or "Unknown",
        reasoning               = lead.get("ai_reasoning") or "N/A",
    )

    completion = await openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a B2B sales email writer for Dhampur Green, an Indian sugar supplier. "
                    "Write professional, personalized outreach emails exactly in the format requested."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    response     = completion.choices[0].message.content
    lines        = response.strip().split("\n")
    subject      = ""
    body_lines   = []
    past_subject = False
    for line in lines:
        if line.startswith("SUBJECT:") and not past_subject:
            subject      = line.replace("SUBJECT:", "").strip()
            past_subject = True
        else:
            body_lines.append(line)

    return subject, "\n".join(body_lines).strip()


async def _send_smtp(to_email: str, subject: str, body: str) -> None:
    """Delegates to app/utils/smtp.py — toggle DUMMY/REAL sending there."""
    await send_email(to_email, subject, body)


# ─── bulk send ────────────────────────────────────────────────────────────────

async def _run_bulk_send() -> dict:
    """
    Core async logic for bulk email sending.
    Extracted so it can be called from the Celery task (and tests) directly.
    """
    now = datetime.now(timezone.utc)

    async with celery_session() as session:
        leads_no_email = (await session.execute(
            select(Lead)
            .where(
                Lead.status == LeadStatus.NEW,
                not_(
                    exists().where(OutreachEmail.lead_id == Lead.id)
                ),
            )
        )).scalars().all()

        # ── 2. Leads with status=NEW whose latest email is still DRAFT ────────
        # Use a subquery for distinct IDs to avoid DISTINCT on json columns.
        draft_lead_ids_rows = (await session.execute(
            select(Lead.id)
            .join(OutreachEmail, OutreachEmail.lead_id == Lead.id)
            .where(
                Lead.status == LeadStatus.NEW,
                OutreachEmail.status == EmailStatus.DRAFT,
            )
            .distinct()
        )).all()
        draft_lead_ids = [r[0] for r in draft_lead_ids_rows]

        leads_draft = (await session.execute(
            select(Lead).where(Lead.id.in_(draft_lead_ids))
        )).scalars().all() if draft_lead_ids else []

        # Deduplicate
        seen = set()
        target_leads = []
        for lead in [*leads_no_email, *leads_draft]:
            if lead.id not in seen:
                seen.add(lead.id)
                target_leads.append(lead)

        # Pre-fetch primary contacts for all target leads in one query
        lead_ids = [l.id for l in target_leads]
        contacts_result = (await session.execute(
            select(Contact)
            .where(Contact.lead_id.in_(lead_ids), Contact.is_primary == True)
        )).scalars().all()
        contact_by_lead = {c.lead_id: c for c in contacts_result}

    # ── Generate + Send outside the session (no long-held DB lock) ────────────
    sent    = []
    skipped = []
    errors  = []

    for lead_obj in target_leads:
        lead     = model_to_dict(lead_obj)
        lead_id  = lead["id"]
        primary  = contact_by_lead.get(lead_id)

        if not primary:
            skipped.append({"lead_id": lead_id, "name": lead["business_name"], "reason": "no contacts found"})
            continue

        to_email = primary.email or ""
        if not to_email:
            skipped.append({"lead_id": lead_id, "name": lead["business_name"], "reason": "contact has no email address"})
            continue

        try:
            subject, body = await _generate_email_content(lead, primary)
        except Exception as exc:
            errors.append({"lead_id": lead_id, "name": lead["business_name"], "error": f"generation failed: {exc}"})
            continue

        try:
            await _send_smtp(to_email, subject, body)
        except Exception as exc:
            errors.append({"lead_id": lead_id, "name": lead["business_name"], "error": f"send failed: {exc}"})
            continue

        # ── Persist the email record and update lead status ──────────────────
        async with celery_session() as session:
            existing_draft = (await session.execute(
                select(OutreachEmail)
                .where(OutreachEmail.lead_id == lead_id, OutreachEmail.status == EmailStatus.DRAFT)
                .order_by(desc(OutreachEmail.generated_at))
                .limit(1)
            )).scalar_one_or_none()

            if existing_draft:
                existing_draft.subject       = subject
                existing_draft.body          = body
                existing_draft.status        = EmailStatus.SENT
                existing_draft.email_type    = EmailType.INITIAL
                existing_draft.sent_at       = now
                existing_draft.sent_to_email = to_email
            else:
                session.add(OutreachEmail(
                    id            = str(uuid.uuid4()),
                    lead_id       = lead_id,
                    lead_name     = lead["business_name"],
                    lead_city     = lead["city"],
                    lead_segment  = lead["segment"],
                    subject       = subject,
                    body          = body,
                    status        = EmailStatus.SENT,
                    email_type    = EmailType.INITIAL,
                    generated_at  = now,
                    sent_at       = now,
                    sent_to_email = to_email,
                ))

            # Mark lead as CONTACTED
            lead_record = (await session.execute(
                select(Lead).where(Lead.id == lead_id)
            )).scalar_one_or_none()
            if lead_record:
                lead_record.status     = LeadStatus.CONTACTED
                lead_record.updated_at = now

            await session.commit()

        sent.append({
            "lead_id":  lead_id,
            "name":     lead["business_name"],
            "to_email": to_email,
            "subject":  subject,
        })

    return {
        "total_processed": len(target_leads),
        "sent":    sent,
        "skipped": skipped,
        "errors":  errors,
    }


@outreach_router.post("/bulk-send")
async def bulk_send_emails():
    """
    Dispatches a Celery task to generate and send personalised emails to all
    'new' leads that have no email or only a draft.

    Returns immediately with a task_id — poll GET /outreach/bulk-send/{task_id}
    for progress / results.
    """
    from app.core.celery_app import celery_app as _celery_app
    task_id = str(uuid.uuid4())
    _celery_app.tasks["send_bulk_emails_task"].apply_async(
        task_id=task_id,
    )
    return {"task_id": task_id, "status": "queued"}


@outreach_router.get("/bulk-send/{task_id}")
async def bulk_send_status(task_id: str):
    """Poll the status of a bulk-send Celery task."""
    from celery.result import AsyncResult
    from app.core.celery_app import celery_app as _celery_app
    result = AsyncResult(task_id, app=_celery_app)
    if result.state == "PENDING":
        return {"task_id": task_id, "status": "pending"}
    if result.state == "STARTED":
        return {"task_id": task_id, "status": "running"}
    if result.state == "SUCCESS":
        return {"task_id": task_id, "status": "completed", "result": result.result}
    if result.state == "FAILURE":
        return {"task_id": task_id, "status": "failed", "error": str(result.result)}
    return {"task_id": task_id, "status": result.state.lower()}


# ─── follow-up helpers ────────────────────────────────────────────────────────

async def _generate_follow_up_content(
    lead: dict,
    primary_contact,
    original_subject: str,
    days_since_sent: int,
) -> tuple[str, str]:
    """Return (subject, body) for a follow-up email using OpenAI."""
    dm         = (primary_contact.name if primary_contact else None) or "Procurement Manager"
    first_name = dm.split()[0] if dm else "Sir/Madam"

    prompt = follow_up_email_prompt(
        business_name    = lead["business_name"],
        segment          = lead["segment"],
        city             = lead["city"],
        dm               = dm,
        first_name       = first_name,
        role             = (primary_contact.role if primary_contact else None) or "F&B Head",
        original_subject = original_subject,
        days_since_sent  = days_since_sent,
    )

    completion = await openai_client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a B2B sales email writer for Dhampur Green, an Indian sugar supplier. "
                    "Write professional, personalized follow-up emails exactly in the format requested."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    response     = completion.choices[0].message.content
    lines        = response.strip().split("\n")
    subject      = ""
    body_lines   = []
    past_subject = False
    for line in lines:
        if line.startswith("SUBJECT:") and not past_subject:
            subject      = line.replace("SUBJECT:", "").strip()
            past_subject = True
        else:
            body_lines.append(line)

    return subject, "\n".join(body_lines).strip()


async def _run_follow_up(follow_up_after_days: int = 3) -> dict:
    """
    Core async logic for follow-up email sending.

    Targets: leads with status=CONTACTED that have a SENT initial email
    whose sent_at is >= follow_up_after_days days ago and no follow-up
    has been sent yet (no email with email_type=FOLLOW_UP exists).

    Extracted so it can be called from the Celery task directly.
    """
    from datetime import timedelta

    now       = datetime.now(timezone.utc)
    cutoff    = now - timedelta(days=follow_up_after_days)

    async with celery_session() as session:
        # Leads already CONTACTED whose initial sent email is old enough
        # but who have NOT yet received a follow-up.
        # Use aliased(OutreachEmail) inside exists() to avoid SQLAlchemy
        # auto-correlating the subquery with the outer join on OutreachEmail.
        FollowUpCheck = aliased(OutreachEmail, flat=True)
        contacted_lead_id_rows = (await session.execute(
            select(Lead.id)
            .join(OutreachEmail, OutreachEmail.lead_id == Lead.id)
            .where(
                Lead.status == LeadStatus.CONTACTED,
                OutreachEmail.status == EmailStatus.SENT,
                OutreachEmail.email_type == EmailType.INITIAL,
                OutreachEmail.sent_at <= cutoff,
                ~exists(
                    select(FollowUpCheck.id)
                    .where(
                        FollowUpCheck.lead_id == Lead.id,
                        FollowUpCheck.email_type == EmailType.FOLLOW_UP,
                    )
                    .correlate(Lead)
                ),
            )
            .distinct()
        )).all()

        contacted_lead_ids = [r[0] for r in contacted_lead_id_rows]

        if not contacted_lead_ids:
            return {"total_processed": 0, "sent": [], "skipped": [], "errors": []}

        # Fetch full Lead rows
        target_leads = (await session.execute(
            select(Lead).where(Lead.id.in_(contacted_lead_ids))
        )).scalars().all()

        # Fetch the most recent INITIAL sent email per lead (for subject context)
        initial_emails_result = (await session.execute(
            select(OutreachEmail)
            .where(
                OutreachEmail.lead_id.in_(contacted_lead_ids),
                OutreachEmail.status    == EmailStatus.SENT,
                OutreachEmail.email_type == EmailType.INITIAL,
            )
            .order_by(desc(OutreachEmail.sent_at))
        )).scalars().all()

        # Keep only the latest initial email per lead
        initial_email_by_lead: dict[str, OutreachEmail] = {}
        for em in initial_emails_result:
            if em.lead_id not in initial_email_by_lead:
                initial_email_by_lead[em.lead_id] = em

        # Fetch primary contacts
        contacts_result = (await session.execute(
            select(Contact)
            .where(Contact.lead_id.in_(contacted_lead_ids), Contact.is_primary == True)
        )).scalars().all()
        contact_by_lead = {c.lead_id: c for c in contacts_result}

    # ── Generate + Send outside the session ───────────────────────────────────
    sent    = []
    skipped = []
    errors  = []

    for lead_obj in target_leads:
        lead    = model_to_dict(lead_obj)
        lead_id = lead["id"]
        primary = contact_by_lead.get(lead_id)

        if not primary:
            skipped.append({"lead_id": lead_id, "name": lead["business_name"], "reason": "no contacts found"})
            continue

        to_email = primary.email or ""
        if not to_email:
            skipped.append({"lead_id": lead_id, "name": lead["business_name"], "reason": "contact has no email address"})
            continue

        original_email   = initial_email_by_lead.get(lead_id)
        original_subject = original_email.subject if original_email else ""
        days_since       = (now - original_email.sent_at).days if original_email and original_email.sent_at else follow_up_after_days

        try:
            subject, body = await _generate_follow_up_content(lead, primary, original_subject, days_since)
        except Exception as exc:
            errors.append({"lead_id": lead_id, "name": lead["business_name"], "error": f"generation failed: {exc}"})
            continue

        try:
            await _send_smtp(to_email, subject, body)
        except Exception as exc:
            errors.append({"lead_id": lead_id, "name": lead["business_name"], "error": f"send failed: {exc}"})
            continue

        # Persist the follow-up email record
        async with celery_session() as session:
            session.add(OutreachEmail(
                id            = str(uuid.uuid4()),
                lead_id       = lead_id,
                lead_name     = lead["business_name"],
                lead_city     = lead["city"],
                lead_segment  = lead["segment"],
                subject       = subject,
                body          = body,
                status        = EmailStatus.FOLLOW_UP_SENT,
                email_type    = EmailType.FOLLOW_UP,
                generated_at  = now,
                sent_at       = now,
                sent_to_email = to_email,
            ))
            # Update lead status to FOLLOW_UP
            lead_obj_db = (await session.execute(
                select(Lead).where(Lead.id == lead_id)
            )).scalar_one_or_none()
            if lead_obj_db:
                lead_obj_db.status = LeadStatus.FOLLOW_UP
            await session.commit()

        sent.append({
            "lead_id":        lead_id,
            "name":           lead["business_name"],
            "to_email":       to_email,
            "subject":        subject,
            "original_email": original_subject,
        })

    return {
        "total_processed": len(target_leads),
        "sent":    sent,
        "skipped": skipped,
        "errors":  errors,
    }


# ─── follow-up endpoints ──────────────────────────────────────────────────────

@outreach_router.post("/follow-up")
async def trigger_follow_up(follow_up_after_days: int = 3):
    """
    Dispatch a Celery task to send follow-up emails to all CONTACTED leads
    whose initial email was sent >= follow_up_after_days days ago with no reply.

    Returns immediately with a task_id.
    Poll GET /outreach/follow-up/{task_id} for results.
    """
    from app.core.celery_app import celery_app as _celery_app
    task_id = str(uuid.uuid4())
    _celery_app.tasks["send_follow_up_emails_task"].apply_async(
        kwargs={"follow_up_after_days": follow_up_after_days},
        task_id=task_id,
    )
    return {"task_id": task_id, "status": "queued", "follow_up_after_days": follow_up_after_days}


@outreach_router.get("/follow-up/{task_id}")
async def follow_up_status(task_id: str):
    """Poll the status of a follow-up Celery task."""
    from celery.result import AsyncResult
    from app.core.celery_app import celery_app as _celery_app
    result = AsyncResult(task_id, app=_celery_app)
    if result.state == "PENDING":
        return {"task_id": task_id, "status": "pending"}
    if result.state == "STARTED":
        return {"task_id": task_id, "status": "running"}
    if result.state == "SUCCESS":
        return {"task_id": task_id, "status": "completed", "result": result.result}
    if result.state == "FAILURE":
        return {"task_id": task_id, "status": "failed", "error": str(result.result)}
    return {"task_id": task_id, "status": result.state.lower()}
