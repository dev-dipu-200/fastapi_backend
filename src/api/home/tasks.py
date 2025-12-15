import os
import base64
import asyncio
import aiohttp
import time
import json
from src.models.url_model import SortUrls
from src.models.user_model import Email, User
from src.configure.database import AsyncSessionLocal
from src.configure.settings import settings
from sqlalchemy import select
from datetime import datetime, timedelta
from src.configure.celery import celery_app
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from msal import ConfidentialClientApplication


@celery_app.task(name="parse_gmail_emails_async")
def parse_gmail_emails_async(users: list[dict]):
    """
    users: list of dicts with keys 'user_id', 'email', 'token_json'
    Example: [{"user_id": "user1", "email": "abc@gmail.com", "token_json": "..."}, ...]
    """

    async def _parse_user(user):
        start_time = time.time()
        user_id = user["user_id"]
        email = user["email"]
        token_json = user["token_json"]

        SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        creds_path = settings.GOOGLE_CLIENT_SECRET_PATH

        if not creds_path or not os.path.exists(creds_path):
            raise FileNotFoundError(f"Credentials file not found at: {creds_path}")

        loop = asyncio.get_event_loop()
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

        # Refresh token if expired
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(User).where(User.user_id == user_id))
                    user_obj = result.scalars().first()
                    if user_obj:
                        user_obj.token_json = json.dumps(creds.to_json())
                        await db.commit()
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = await loop.run_in_executor(None, lambda: flow.run_local_server(port=8080))
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(User).where(User.user_id == user_id))
                    user_obj = result.scalars().first()
                    if user_obj:
                        user_obj.token_json = json.dumps(creds.to_json())
                        await db.commit()

        service = build('gmail', 'v1', credentials=creds, cache_discovery=False)

        async def fetch_message_batch(messages):
            batch_results = []

            def callback(request_id, response, exception):
                if exception:
                    batch_results.append({"message_id": request_id, "error": str(exception)})
                    return

                payload = response.get('payload', {})
                headers = payload.get('headers', [])
                subject = next((h['value'] for h in headers if h.get('name') == 'Subject'), "")
                sender = next((h['value'] for h in headers if h.get('name') == 'From'), "")
                body = ""

                if 'data' in payload.get('body', {}):
                    data = payload['body'].get('data', '')
                    if data:
                        body = base64.urlsafe_b64decode(data.encode()).decode()
                else:
                    for part in payload.get('parts', []):
                        data = part.get('body', {}).get('data', '')
                        if data:
                            body = base64.urlsafe_b64decode(data.encode()).decode()
                            break

                batch_results.append({
                    "message_id": request_id,
                    "subject": subject,
                    "sender": sender,
                    "body": body,
                })

            batch = service.new_batch_http_request()
            for msg in messages:
                batch.add(
                    service.users().messages().get(userId='me', id=msg['id'], format='full'),
                    callback=callback
                )

            await loop.run_in_executor(None, batch.execute)
            return batch_results

        # Fetch latest messages
        results = await loop.run_in_executor(
            None,
            lambda: service.users().messages().list(userId='me', maxResults=5).execute()
        )
        messages = results.get('messages', [])
        parsed = await fetch_message_batch(messages) if messages else []

        # Store parsed emails in DB
        async with AsyncSessionLocal() as db:
            for email_data in parsed:
                if "error" not in email_data:
                    existing = await db.execute(
                        select(Email).where(Email.message_id == email_data['message_id'])
                    )
                    if not existing.scalars().first():
                        db.add(Email(
                            message_id=email_data['message_id'],
                            subject=email_data['subject'],
                            sender=email_data['sender'],
                            body=email_data['body'],
                            user_id=user_id
                        ))
            await db.commit()

        end_time = time.time()
        return {"user_id": user_id, "emails": parsed, "execution_time_ms": round((end_time - start_time) * 1000, 2)}

    async def _parse_all_users():
        results = []
        for user in users:
            try:
                result = await _parse_user(user)
                results.append(result)
            except Exception as e:
                results.append({"user_id": user.get("user_id"), "error": str(e)})
        return results

    try:
        final_result = asyncio.run(_parse_all_users())
        print(f"Gmail Emails Parsed for {len(final_result)} users")
        return final_result
    except Exception as e:
        print(f"Error in Gmail task for multiple users: {e}")
        raise



@celery_app.task(name="fetch_emails_from_db_async")
def fetch_emails_from_db_async(user_id: str = None, limit: int = 100):
    async def _fetch_emails():
        start_time = time.time()
        async with AsyncSessionLocal() as db:
            query = select(Email).order_by(Email.created_at.desc()).limit(limit)
            if user_id:
                query = query.where(Email.user_id == user_id)
            result = await db.execute(query)
            emails = result.scalars().all()
            parsed = [
                {
                    "message_id": email.message_id,
                    "subject": email.subject,
                    "sender": email.sender,
                    "body": email.body,
                    "created_at": email.created_at.isoformat()
                }
                for email in emails
            ]
        end_time = time.time()
        return {"emails": parsed, "execution_time_ms": round((end_time - start_time) * 1000, 2)}

    try:
        result = asyncio.run(_fetch_emails())
        print(f"📧 Emails Fetched for User {user_id} (took {result['execution_time_ms']} ms)")
        return result
    except Exception as e:
        print(f"Error in fetch_emails task: {e}")
        raise


@celery_app.task(name="parse_outlook_emails_async")
def parse_outlook_emails_async():
    async def _parse_outlook_emails():
        start_time = time.time()
        CLIENT_ID = settings.OUTLOOK_CLIENT_ID
        TENANT_ID = settings.OUTLOOK_TENANT_ID
        CLIENT_SECRET = settings.OUTLOOK_CLIENT_SECRET
        authority = f"https://login.microsoftonline.com/{TENANT_ID}"
        scope = ["https://graph.microsoft.com/.default"]

        app = ConfidentialClientApplication(
            CLIENT_ID, authority=authority, client_credential=CLIENT_SECRET
        )
        loop = asyncio.get_event_loop()
        token = await loop.run_in_executor(None, lambda: app.acquire_token_for_client(scopes=scope))
        access_token = token.get("access_token")
        if not access_token:
            raise Exception("Failed to acquire Outlook access token")

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {access_token}"}
            async with session.get("https://graph.microsoft.com/v1.0/me/messages?$top=5", headers=headers) as response:
                messages = (await response.json()).get("value", [])
            parsed = [
                {
                    "message_id": message.get("id"),
                    "subject": message.get("subject", ""),
                    "sender": message.get("from", {}).get("emailAddress", {}).get("address", ""),
                    "body": message.get("body", {}).get("content", "")
                }
                for message in messages
            ]
        end_time = time.time()
        return {"emails": parsed, "execution_time_ms": round((end_time - start_time) * 1000, 2)}

    try:
        result = asyncio.run(_parse_outlook_emails())
        print(f"📧 Outlook Emails Parsed (took {result['execution_time_ms']} ms):", result['emails'])
        return result
    except Exception as e:
        print(f"Error in Outlook task: {e}")
        raise


@celery_app.task(name="expire_urls_async")
def expire_urls_async(batch_size=1000):
    async def _expire_urls():
        start_time = time.time()
        async with AsyncSessionLocal() as db:
            thirty_days_ago = datetime.now() - timedelta(days=30)
            while True:
                result = await db.execute(
                    SortUrls.__table__.select()
                    .where(SortUrls.created_at < thirty_days_ago)
                    .limit(batch_size)
                )
                expired_urls = result.scalars().all()
                if not expired_urls:
                    break
                for url in expired_urls:
                    await db.delete(url)
                await db.commit()
                print(f"Deleted batch of {len(expired_urls)} URLs")
        end_time = time.time()
        return {"message": "Expired URLs older than 30 days have been deleted.", "execution_time_ms": round((end_time - start_time) * 1000, 2)}

    try:
        result = asyncio.run(_expire_urls())
        print(f"Expired URLs task (took {result['execution_time_ms']} ms):", result['message'])
        return result
    except Exception as e:
        print(f"Error in expire_urls task: {e}")
        raise
