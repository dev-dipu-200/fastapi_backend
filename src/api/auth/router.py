from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .schema import Login, Registraion
from .service import create_user, login_user, get_current_user
from src.configure.database import get_db
router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

@router.post("/register")
async def register(payload: Registraion, db: Session = Depends(get_db)):
    response = await  create_user(payload=payload, db=db)
    return {"result": response}

@router.post("/login")
async def login(payload: Login, db: Session = Depends(get_db)):
    response = await login_user(payload=payload, db=db)
    return {"result": response}


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    
    return {"result": current_user}

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"message": "Logout successful"}