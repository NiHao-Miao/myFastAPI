from fastapi import FastAPI, Path, Query, Depends
from pydantic import BaseModel, Field
app = FastAPI()

@app.get("/")
async def read_root():
    return {"message": "Hello, FastAPI!"}

@app.get("/items/{item_id}")
async def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}

@app.get("/hello")
async def hello():
    return {"message": "你好，Fastapi"}

@app.get("/user/hello")
async def hello():
    return {"message": "你好，Fastapi,你好吗"}

@app.get("/userid/{id}")
async def user(id: int):
    return {"id":id, "username": f"用户名为{id}"}

@app.get("/searchbook/{id}")
async def search(id:int = Path(..., gt=1, lt=11,description="查询范围在2-10之间")):
    return {"id":id, "bookname":f"查询到了{id}"}

@app.get("/fenleiid/{id}")
async def fenlei(id:int = Path(..., gt=0,lt=101,description="id范围为1~100")):
    return {"id":id, "content":f"id分类为{id}"}

@app.get("/fenleiname/{name}")
async def fenlei(name:str = Path(..., min_length=2,max_length=10,description="name范围为2~10")):
    return {"name":name, "content":f"name分类为{name}"}

@app.get("/querybook/")
async def quert(
    category: str = Query(f"Python开发",min_length=5,max_length=255),
    price:float = Query(...,gt=49,lt=101,description="50~100之间")
):
    return {"category":category, "price":price}

class Book(BaseModel):
    name:str = Field(..., min_length=2, max_length=20, description="书名")
    author:str = Field(..., min_length=2, max_length=10, description="作者")
    edit:str = Field("人民出版社", description="出版社")
    price:float = Field(..., gt=0, description="售价")
@app.post("/book/")
async def book(book:Book):
    return book


async def common_paraments(
        skip:int = Query(0, ge=0),
        limit:int = Query(10,le=60),
):
    return {"skip":skip, "limit":limit}

@app.get("/")
async def get_new(common=Depends(common_paraments)):
    return common