from jinja2 import Environment, FileSystemLoader, select_autoescape

templates_env = Environment(
    loader=FileSystemLoader("app/templates"),
    autoescape=select_autoescape(["html", "xml"])
)

def render_email_template(template_name: str, context: dict) -> str:
    template = templates_env.get_template(template_name)
    return template.render(**context)
