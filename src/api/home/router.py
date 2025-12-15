import os
import asyncio
import logging
from src.models.url_model import SortUrls
from src.models.click_model import Clicks
from src.models.user_model import User, Email
from src.configure.database import get_db as get_async_db
from datetime import datetime
from src.api.home.service import (
    create_sort_ulr,
    get_menual_long_url,
    update_menual_long_url,
)
from pydantic import BaseModel
from src.configure.celery import celery_app
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
from src.chains.simple_chain import open_ai_question
from fastapi import APIRouter, HTTPException, Request, Depends
from src.api.auth.service import get_current_user
from src.api.home.tasks import parse_gmail_emails_async, parse_outlook_emails_async
from google_auth_oauthlib.flow import InstalledAppFlow

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Home"])

class Question(BaseModel):
    question: str

class UserIdsList(BaseModel):
    user_ids: list[str]  # Fixed from user_emails

@router.get("/{slug}")
async def get_long_url(slug: str, db: AsyncSession = Depends(get_async_db)):
    """Retrieves the original long URL using the short slug.
    Returns a 404 if the slug doesn’t exist.
    """
    logger.info(f"Fetching long URL for slug: {slug}")
    try:
        response = await get_menual_long_url(slug, db)
        if not response:
            logger.warning(f"Slug {slug} not found")
            raise HTTPException(status_code=404, detail="Slug not found")
        return response
    except Exception as e:
        logger.error(f"Error fetching long URL for slug {slug}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/shorten")
async def shorten_url(long_url: str, db: AsyncSession = Depends(get_async_db)):
    """Shortens a long URL and returns the shortened version.
    If the long URL already exists, return the existing short link.
    """
    logger.info(f"Shortening URL: {long_url}")
    try:
        response = await create_sort_ulr(long_url, db)
        logger.info(f"Shortened URL created: {response}")
        return response
    except Exception as e:
        logger.error(f"Error shortening URL {long_url}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{slug}")
async def update_long_url(
    slug: str, new_long_url: str, db: AsyncSession = Depends(get_async_db)
):
    """Updates the long URL associated with an existing slug.
    Validates the new URL and applies expiration logic.
    """
    logger.info(f"Updating slug {slug} to new long URL: {new_long_url}")
    try:
        response = await update_menual_long_url(slug, new_long_url, db)
        if not response:
            logger.warning(f"Slug {slug} not found for update")
            raise HTTPException(status_code=404, detail="Slug not found")
        logger.info(f"Updated slug {slug} successfully")
        return response
    except Exception as e:
        logger.error(f"Error updating slug {slug}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/short.ly/{short_code}")
async def redirect_short_url(
    short_code: str, request: Request, db: AsyncSession = Depends(get_async_db)
):
    """Redirects short URL to original URL and tracks clicks."""
    full_short_url = f"http://localhost:8000/short.ly/{short_code}"
    logger.info(f"Redirecting short URL: {full_short_url}")

    short_url = await db.query(SortUrls).filter_by(short_url=full_short_url).first()
    if not short_url:
        logger.warning(f"Short URL {full_short_url} not found")
        raise HTTPException(status_code=404, detail="Short URL not found")

    click = await db.query(Clicks).filter_by(sort_url_id=short_url.id).first()
    if click:
        click.click_count += 1
        click.last_clicked_at = datetime.now()
        await db.commit()
        await db.refresh(click)
        logger.info(f"Updated click count for sort_url_id {short_url.id}: {click.click_count}")
    else:
        logger.info(f"No click found for sort_url_id {short_url.id}, creating new click")
        click = Clicks(
            sort_url_id=short_url.id, click_count=1, last_clicked_at=datetime.now()
        )
        db.add(click)
        await db.commit()
        await db.refresh(click)

    return {"click_count": click.click_count, "last_clicked_at": click.last_clicked_at}

@router.post("/ask")
async def ask_open_ai(question: Question):
    """Queries Open AI with a user-provided question."""
    # logger.info(f"Processing question: {question.question}")
    try:
        answer = await open_ai_question(question.question)
        # logger.info(f"Received answer for question: {answer.strip()}")
        return {"question": question.question, "answer": answer.strip()}
    except Exception as e:
        logger.error(f"Error processing question '{question.question}': {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/emails/gmail")
async def trigger_gmail(
    user_ids_list: UserIdsList,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """Triggers Gmail email parsing for specified user_ids."""
    logger.info(f"User {current_user.get('email')} initiating Gmail parsing for user_ids: {user_ids_list.user_ids}")
    
    # Fetch users based on role
    if current_user.get("role") != "admin":
        current_user_record = await db.execute(
            select(User).where(User.email == current_user["email"])
        ).scalar_one_or_none()
        if not current_user_record:
            logger.error(f"Current user {current_user['email']} not found")
            raise HTTPException(status_code=404, detail="Current user not found")
        org_name = current_user_record.organization__org_name
        users = await db.query(User).filter_by(
            is_active=True, organization__org_name=org_name
        ).all()
    else:
        users = await db.execute(select(User).where(User.is_active == True))
        users = users.scalars().all()

    # Filter valid users with tokens
    valid_users = [
        {"user_id": user.user_id, "email": user.email, "token_json": user.token_json}
        for user in users
        if user.user_id in user_ids_list.user_ids and user.token_json
    ]

    if not valid_users:
        logger.warning("No valid users with OAuth tokens found")
        raise HTTPException(status_code=400, detail="No users with valid OAuth tokens found")

    # Trigger the new Celery task with all users at once
    logger.info(f"Triggering Gmail parsing for {len(valid_users)} users")
    parse_gmail_emails_async.delay(valid_users)

    return {"status": f"Gmail email parsing started for {len(valid_users)} users."}


@router.get("/users/list")
async def get_users(
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """Fetches list of active users, restricted by role/organization."""
    logger.info(f"User {current_user.get('email')} fetching users")
    
    if current_user.get("role") != "admin":
        current_user_record = await db.execute(select(User).where(User.email == current_user["email"])).scalar_one_or_none()
        if not current_user_record:
            logger.error(f"Current user {current_user['email']} not found")
            raise HTTPException(status_code=404, detail="Current user not found")
        users = await db.execute(select(User).filter_by(
            is_active=True, organization__org_name=current_user_record.organization__org_name
        ))
        users = users.scalars().all()  # Extract list from Result
    else:
        users = await db.execute(select(User).filter_by(is_active=True))
        users = users.scalars().all()

    return [{"user_id": user.user_id, "email": user.email, "role": user.role} for user in users]

@router.post("/auth/gmail/{user_id}")
async def auth_gmail(
    user_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """Authenticates Gmail for a user and stores token_json."""
    logger.info(f"User {current_user.get('email')} initiating Gmail auth for user_id: {user_id}")
    
    user = await db.execute(select(User).filter_by(user_id=user_id))
    user = user.scalar_one_or_none()
    if not user:
        logger.error(f"User with user_id {user_id} not found")
        raise HTTPException(status_code=404, detail="User not found")
    if current_user.get("role") != "admin" and current_user.get("email") != user.email:
        logger.warning(f"User {current_user.get('email')} not authorized to authenticate user_id {user_id}")
        raise HTTPException(status_code=403, detail="Not authorized to authenticate this user")

    from src.configure.settings import settings

    user_email = user.email  # Preload to avoid lazy loading
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    creds_path = settings.GOOGLE_CLIENT_SECRET_PATH
    if not creds_path or not os.path.exists(creds_path):
        logger.error(f"Google credentials not found at {creds_path}")
        raise HTTPException(status_code=500, detail="Google credentials not configured")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
        creds = await asyncio.get_event_loop().run_in_executor(None, lambda: flow.run_local_server(port=8080))
        user.token_json = creds.to_json()
        await db.commit()
        logger.info(f"Gmail authenticated for user_id {user_id} (email: {user_email})")
        return {"status": f"Authenticated Gmail for {user_email}"}
    except Exception as e:
        logger.error(f"Failed to authenticate Gmail for user_id {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Gmail authentication failed: {str(e)}")

@router.post("/emails/outlook")
async def trigger_outlook(
    user_ids_list: UserIdsList,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """Triggers Outlook email parsing for specified user_ids."""
    logger.info(f"User {current_user.get('email')} initiating Outlook parsing for user_ids: {user_ids_list.user_ids}")
    
    if current_user.get("role") != "admin":
        current_user_record = await db.query(User).filter_by(email=current_user["email"]).first()
        if not current_user_record:
            logger.error(f"Current user {current_user['email']} not found")
            raise HTTPException(status_code=404, detail="Current user not found")
        org_name = current_user_record.organization__org_name
        users = await db.query(User).filter_by(
            is_active=True, organization__org_name=org_name
        ).all()
    else:
        users = await db.query(User).filter_by(is_active=True).all()

    valid_users = [
        {"user_id": user.user_id, "email": user.email, "outlook_token_json": user.outlook_token_json}
        for user in users
        if user.user_id in user_ids_list.user_ids and user.outlook_token_json
    ]

    if not valid_users:
        logger.warning("No valid users with Outlook OAuth tokens found")
        raise HTTPException(status_code=400, detail="No users with valid Outlook OAuth tokens found")

    for user in valid_users:
        logger.info(f"Triggering Outlook parsing for user_id: {user['user_id']}")
        celery_app.send_task(
            'parse_outlook_emails_async',
            kwargs={
                'user_id': user['user_id'],
                'email': user['email'],
                'token_json': user['outlook_token_json']
            }
        )

    return {"status": f"Outlook email parsing started for {len(valid_users)} users."}