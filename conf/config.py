# itzmy/conf/config.py
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"




# 配置文件的 模型类 校验
class Settings(BaseSettings):

    # LLM
    llm_api_key: str
    llm_model: str
    llm_base_url: str

    # 数据库
    database_url: str

    # 商城 API
    commerce_api_base_url: str

    # 服务器
    app_host: str
    app_port: int

    # 数字人（魔珐星云），未配置时为空串，接口会返回 configured=False
    digital_human_app_id: str = ""
    digital_human_app_secret: str = ""
    digital_human_gateway_server: str = "https://nebula-agent.xingyun3d.com/user/v1/ttsa/session"

    # 视觉模型（图片识别，SiliconFlow OpenAI 兼容接口）
    vl_model: str = "Qwen/Qwen3-VL-30B-A3B-Instruct"

    # FAQ 语义检索（embedding 模型，走同一个 OpenAI 兼容网关）
    embedding_model: str = "BAAI/bge-m3"

    # 管理后台密码（看板/FAQ 管理的写操作需要 X-Admin-Token 头）
    # A8：删除弱默认密码 admin888，改为必填项，缺失时启动报错
    admin_password: str


    # 从.env文件中读取配置信息
    # 如果读取真实环境变量，则不写这句话
    # extra="ignore" 表示忽略.env那个文件中有，setting类没有写的配置项，不会报错
    # env_file_encoding：如果遇到乱码问题则添加这个属性解决
    # 注意这里对象名必须叫model_config ，而且必须定义，否则配置会被回收
    # 继承 BaseSettings   里面也提供一系列 默认 的属性
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore", env_file_encoding="utf-8")

settings = Settings()


if __name__ == '__main__':

    a = int(os.getenv("APP_PORT")) # int
    print(type(a)) # int   NoneType
    # from itzmy.conf.config import settings
    # 自动为我们做了 类型转换
    print(type(settings.database_url))

