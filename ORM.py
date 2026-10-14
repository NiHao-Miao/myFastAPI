from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import DateTime, Float, String, func, select
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

app = FastAPI()

#1.创建异步引擎
ASYNC_DATABASE_URL = "mysql+aiomysql://root:123456@localhost:3306/fastapi?charset=utf8"
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo =True,
    pool_size = 10,
    max_overflow = 20
)

#2.定义模型类：基类+表对应的模型类
class Base(DeclarativeBase):
    create_time: Mapped[datetime] = mapped_column(
    DateTime,
    insert_default=func.now(),
    comment="创建时间"
    )

    update_time: Mapped[datetime] = mapped_column(
    DateTime,
    insert_default=func.now(),
    onupdate=func.now(),
    comment="更新时间"
    )

class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(primary_key=True, comment= "书籍ID")
    name: Mapped[str] = mapped_column(String(100), comment="书名")
    author: Mapped[str] = mapped_column(String(100), comment="作者")
    price: Mapped[float] = mapped_column(Float, comment="价格")
    publisher: Mapped[str] = mapped_column(String(100), comment="出版社")

class User(Base):
    __tablename__ = "users"
    id:Mapped[int] = mapped_column(primary_key=True, comment= "用户ID")
    username: Mapped[str] = mapped_column(String(100), comment="用户名")
    password: Mapped[str] = mapped_column(String(100), comment="密码")

#3.创建表
async def create_tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield
    await async_engine.dispose()

app = FastAPI(lifespan=lifespan)
@app.get("/")
async def root():
    return {"message": "nihao orm"}

#需求：查询功能的接口，查询图书 -> 依赖注入：创建依赖项获取数据库会话+depends 注入路由处理函数

AsyncSessionLocal = async_sessionmaker(
    bind = async_engine,
    class_ = AsyncSession,
    expire_on_commit=False
)
#依赖项
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()
#条件查询和模糊查询
@app.get("/book/books")
async def get_book_list(db: AsyncSession = Depends(get_db)):
    # result = await db.execute(select(Book))
    # book = result.scalars().all()
    # book = result.scalars().first()
    book = await db.get(Book, 9)
    return book

@app.get("/book/get_book/{book_id}")
async def get_book_list(book_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    return book

@app.get("/book/search_book")
async def search_book(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Book).where(Book.price>= 20))
    books = result.scalars().all()
    return books

@app.get("/book/tiaojiansearch")
async def tiaojiansearch(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Book).where(Book.publisher.like("人%")))
    books = result.scalars().all()
    return books

#聚合查询
@app.get("/book/count")
async def count(db: AsyncSession = Depends(get_db)):
    # result = await db.execute(func.count(Book.id))
    result = await db.execute(func.max(Book.price))
    count = result.scalar()
    return {"count": count}

#分页查询
@app.get("/book/get_books")
async def get_books(
    page: int = 2,
    page_size:int = 3,
    db: AsyncSession = Depends(get_db)
):
    skip = (page - 1) * page_size
    result = await db.execute(select(Book).offset(skip).limit(page_size))
    books = result.scalars().all()
    return books

#新增数据
class BookBase(BaseModel):
    id:int
    name: str
    author: str
    price: float
    publisher: str

@app.post("/book/add_book")
async def add_book(book: BookBase, db:AsyncSession = Depends(get_db)):
    book_obj = Book(**book.__dict__)
    db.add(book_obj)
    await db.commit()
    return book_obj 

#更新(修改)
class BookUpdate(BaseModel):
    name: str
    author: str
    price: float
    publisher: str
@app.put("/book/update_book/{book_id}")
async def update_book(book_id: int, data: BookUpdate, db: AsyncSession = Depends(get_db)):
    book = await db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    book.name = data.name
    book.author = data.author
    book.price = data.price
    book.publisher = data.publisher
    await db.commit()
    return book

#删除
@app.delete("/book/delete_book/{book_id}")
async def delete_book(book_id: int, db: AsyncSession = Depends(get_db)):
    book = await db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    await db.delete(book)
    await db.commit()
    return {"message": "Book deleted successfully"}