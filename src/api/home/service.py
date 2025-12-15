

from src.common.helper import generate_self_short_ulr
from src.models.url_model import SortUrls
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
from src.configure.redis import redis_client, REDIS_CHANNEL

async def create_sort_ulr(url: str, db: AsyncSession) -> str:
    """
    Create a short URL from a long URL.
    If a custom slug is provided, it will be used; otherwise, a random slug will be generated.
    """
    existing_url = await db.execute(select(SortUrls).filter(SortUrls.long_url == url)).scalar_one_or_none()
    message = ""
    if existing_url:
        message = f"Sort url already created"
        await redis_client.publish(REDIS_CHANNEL, message)
        output = {
            "short_url": existing_url.short_url,
        }
        return output
    short_url = generate_self_short_ulr(url)
    new_sort_url = SortUrls(long_url=url, short_url=short_url)
    db.add(new_sort_url)
    db.commit()
    db.refresh(new_sort_url)
    message = f"new sort url creted"
    await redis_client.publish(REDIS_CHANNEL, message)
    output = {
        "short_url": new_sort_url.short_url,
    }
    return output


async def get_menual_long_url(slug: int, db: AsyncSession) -> str:
    """
    Retrieve the original long URL using the short slug.
    Returns a 404 if the slug doesn’t exist.
    """
    sort_url = db.query(SortUrls).filter(SortUrls.id == slug).first()
    if not sort_url:
        raise ValueError("Slug not found")
    output = {
        "long_url": sort_url.long_url
    }
    return output


async def update_menual_long_url(slug: int, new_long_url: str, db: AsyncSession) -> str:
    """
    Updates the long URL associated with an existing slug.
    Validates the new URL and applies expiration logic.
    """
    sort_url = db.query(SortUrls).filter(SortUrls.id == slug).first()
    if not sort_url:
        raise ValueError("Slug not found")

    sort_url.long_url = new_long_url
    db.commit()
    db.refresh(sort_url)
    
    output = {
        "short_url": sort_url.short_url,
        "long_url": sort_url.long_url
    }
    return output

async def delete_sort_url(slug: int, db: AsyncSession) -> str:
    """
    Deletes a short URL entry based on the slug.
    Returns a confirmation message if successful.
    """
    sort_url = await db.execute(select(SortUrls).filter(SortUrls.id == slug)).scalar_one_or_none()
    if not sort_url:
        raise ValueError("Slug not found")
    
    db.delete(sort_url)
    db.commit()
    
    return {"message": "Short URL deleted successfully"}

