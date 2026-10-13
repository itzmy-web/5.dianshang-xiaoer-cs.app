# itzmy/main.py

"""
启动uvicorn
"""
import os

import uvicorn

from conf.config import settings

if __name__ == '__main__':
    uvicorn.run(
        app="api.app:app",
        host=os.getenv("HOST", settings.app_host),
        port=int(os.getenv("PORT", str(settings.app_port)))
    )
