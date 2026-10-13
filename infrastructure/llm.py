# itzmy/infrastructure/llm.py

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from conf.config import settings

"""
如果没有 BaseChatModel，你可能需要：
为每个 AI 厂商写不同的代码（OpenAI 一套、百度一套、阿里一套...）
处理各种复杂的 API 调用细节
有了它之后：
统一标准：不管换哪个 AI 模型，代码写法都一样
简化操作：只需要关心"问什么"，不用关心"怎么问"
"""
llm: BaseChatModel = init_chat_model(
    model=settings.llm_model,
    model_provider="openai",
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
    temperature=0 # 温度   设置为0？
)

if __name__ == '__main__':
    print(llm.invoke("你好").content)

"""请认真阅读
先说 temperature 本身是什么。大模型生成每个词（token）时，其实是在算一张“下一个词的概率分布表”——比如“请告诉我你的订单”后面可能是“号”(60%)、“编码”(20%)、“信息”(15%)。temperature 就是给这张概率表“加权”的旋钮：

temperature 高（如 1.5）：概率被拉平，本来 60% 的选项可能只比 5% 的选项略强，模型敢选冷门词 → 输出更有创意、更多样，但也更容易跑偏
temperature 低（如 0.2）：概率被拉开差距，头部选项更占优 → 输出更保守、更可预测
temperature = 0：几乎就是“每次都选概率最高的那个词”（贪心解码）→ 同样的问题给同样的回答，最大程度可复现

那为什么这个项目要设 0？关键在你们项目里 LLM 的角色。这里的 LLM 不是陪你聊天的，而是当“决策中枢”用的。这种场景对 LLM 的要求是“稳定、精确、守格式”，而不是“有创意”。如果 temperature 高，同样一句“我要退 A001 那单”可能这次吐出合法 JSON、下次多打个引号、下又冒出个命令名拼错——整个流程引擎的解析就崩了。
"""