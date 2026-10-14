# from passlib.context import CryptContext

# #创建摸吗上下文
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# #密码哈希函数
# def hash_password(password: str):
#     return pwd_context.hash(password)

# # #验证密码
# # def verify_password(password: str, hashed_password: str):
# #     return pwd_context.verify(password, hashed_password)

import bcrypt

def hash_password(password: str) -> str:
    pw = password.encode('utf-8')[:72]                    # 截断到 72 字节
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        password.encode('utf-8')[:72],                    # 校验时也要同样截断！
        hashed_password.encode('utf-8')
    )