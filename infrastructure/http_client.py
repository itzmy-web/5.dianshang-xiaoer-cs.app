# itzmy/infrastructure/http_client.py
"""
httpx 和 requests 是同一类东西——都是 Python 的 HTTP 客户端库，干一样的活：发 GET/POST、带请求头、传参数、处理响应。你平时怎么用 requests，httpx 基本就怎么用，它的 API 就是照着 requests 设计的，httpx.get()、r.json() 这些写法几乎可以无缝互换
"""
import asyncio
from httpx import AsyncClient
# 全局变量
http_client: AsyncClient | None = None
# 初始化
def init_http_client():
    global http_client
    http_client = AsyncClient(timeout=10.0) # 初始化了一个 请求对象 打开浏览器
# 关闭
async def close_http_client():
    if http_client is not None: # 不为none 关闭之前 先 是不是真的有这个客户端
        await http_client.aclose()

# 异步  请求一个 特别慢 （后台慢慢进行）  下一个任务

if __name__ == '__main__':
    from conf.config import settings
    async def test():
        init_http_client()
        result = await http_client.get(f'{settings.commerce_api_base_url}/users/u1001/orders') # 阻塞
        print(result.json())

        await close_http_client()


    asyncio.run(test())

"""
#同步方式
# r = httpx.get('http://localhost:18081/users/u1001/orders')
# print(r.json())

#异步方式
# async def test():
#     async with httpx.AsyncClient() as client:
#         r = await client.get('http://localhost:18081/users/u1001/orders')
#         print(r.json()['data']['user_id'])
# asyncio.run(test())
"""
