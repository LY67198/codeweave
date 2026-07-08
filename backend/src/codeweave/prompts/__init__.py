"""Jinja2 prompt 模板加载器。"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TPL_DIR = Path(__file__).parent
_env = Environment(loader=FileSystemLoader(str(_TPL_DIR)), autoescape=False)


def render(template_name: str, **vars: object) -> str:
    return _env.get_template(template_name).render(**vars)