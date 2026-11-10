
"""AgentFlow 提示词模板管理。"""

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


PROMPT_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=1)
def get_prompt_environment() -> Environment:
    """创建并缓存 Jinja2 模板环境。"""

    return Environment(
        loader=FileSystemLoader(str(PROMPT_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_prompt(
    template_name: str,
    **variables: object,
) -> str:
    """加载并渲染提示词模板。"""

    environment = get_prompt_environment()
    template = environment.get_template(template_name)

    return template.render(**variables)
