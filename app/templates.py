import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from config import BASE_DIR

_templates_dir = os.path.join(BASE_DIR, 'templates')
_env = Environment(
    loader=FileSystemLoader(_templates_dir),
    autoescape=select_autoescape(['html', 'xml']),
    trim_blocks=True,
    lstrip_blocks=True,
)

def render_template(template_name, context=None):
    if context is None:
        context = {}
    template = _env.get_template(template_name)
    return template.render(**context)

def render_partial(template_name, context=None):
    return render_template(template_name, context)
