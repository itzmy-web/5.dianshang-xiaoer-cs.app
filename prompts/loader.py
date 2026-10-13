# prompts/loader.py
from pathlib import Path


def load_prompt(prompt_file_name: str) -> str:
    """
    加载模板文件
    :param prompt_file_name: 模板文件名
    :return: 模板字符串
    """
    prompt_file_path = Path(__file__).resolve().parents[0] / "jinja2" / f"{prompt_file_name}.jinja2"
    return prompt_file_path.read_text(encoding="utf-8")


if __name__ == '__main__':
    result = load_prompt("clarify_respond")
    print(result)
    print(type(result))