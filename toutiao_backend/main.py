from fastapi import FastAPI
from utils.exception_handlers import register_exception_handlers
from routers import news, users, favorite, history
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
register_exception_handlers(app)
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/")
async def hello():
    return {"message": "你好"}
#挂在路由
app.include_router(news.router)
app.include_router(users.router)
app.include_router(favorite.router)
app.include_router(history.router)
